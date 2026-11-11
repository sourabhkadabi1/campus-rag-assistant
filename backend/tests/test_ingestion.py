"""
Tests for the ingestion pipeline's pure functions:
  - estimate_tokens
  - detect_chapters
  - chunk_text
  - _split_into_chunks

No database or embedding model required.
"""

from __future__ import annotations

import pytest

from app.services.ingestion import (
    ChapterInfo,
    PageContent,
    TextChunk,
    _split_into_chunks,
    chunk_text,
    detect_chapters,
    estimate_tokens,
)


# ── estimate_tokens ───────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 1  # min 1

    def test_short(self):
        # 12 chars → ~3 tokens
        assert estimate_tokens("Hello world!") == 3

    def test_long(self):
        text = "word " * 200  # 1000 chars → ~250 tokens
        assert 240 <= estimate_tokens(text) <= 260


# ── detect_chapters ───────────────────────────────────────────────


class TestDetectChapters:
    def _pages(self, texts: list[str]) -> list[PageContent]:
        return [PageContent(page_num=i + 1, text=t) for i, t in enumerate(texts)]

    def test_basic_chapter(self):
        pages = self._pages(["Chapter 1: Introduction\nSome body text."])
        chs = detect_chapters(pages)
        assert len(chs) == 1
        assert chs[0].chapter_no == 1
        assert chs[0].title == "Introduction"
        assert chs[0].heading_type == "chapter"

    def test_unit_heading(self):
        pages = self._pages(["Unit 3 - Data Structures\nContent here."])
        chs = detect_chapters(pages)
        assert len(chs) == 1
        assert chs[0].chapter_no == 3
        assert chs[0].heading_type == "unit"

    def test_module_heading(self):
        pages = self._pages(["Module 2: Databases\nDetails."])
        chs = detect_chapters(pages)
        assert len(chs) == 1
        assert chs[0].chapter_no == 2
        assert chs[0].heading_type == "module"

    def test_numbered_heading(self):
        pages = self._pages(["1. Getting Started\nFirst page content."])
        chs = detect_chapters(pages)
        assert len(chs) == 1
        assert chs[0].chapter_no == 1
        assert chs[0].title == "Getting Started"

    def test_multiple_chapters_across_pages(self):
        pages = self._pages([
            "Chapter 1: Intro\nText.",
            "Some middle page.",
            "Chapter 2: Arrays\nMore text.",
            "Chapter 3: Sorting\nEven more.",
        ])
        chs = detect_chapters(pages)
        assert len(chs) == 3
        assert [c.chapter_no for c in chs] == [1, 2, 3]
        assert chs[0].page_start == 1
        assert chs[1].page_start == 3
        assert chs[2].page_start == 4

    def test_deduplication(self):
        """Same chapter number on two pages → keep first."""
        pages = self._pages([
            "Chapter 1: Intro\nText.",
            "Chapter 1: Intro (continued)\nMore text.",
        ])
        chs = detect_chapters(pages)
        assert len(chs) == 1
        assert chs[0].page_start == 1

    def test_no_chapters(self):
        pages = self._pages(["Just some regular text.\nNothing here."])
        chs = detect_chapters(pages)
        assert len(chs) == 0

    def test_case_insensitive(self):
        pages = self._pages(["CHAPTER 5: ADVANCED TOPICS\nContent."])
        chs = detect_chapters(pages)
        assert len(chs) == 1
        assert chs[0].chapter_no == 5

    def test_ch_abbreviation(self):
        pages = self._pages(["Ch. 7 Graph Algorithms\nText."])
        chs = detect_chapters(pages)
        assert len(chs) == 1
        assert chs[0].chapter_no == 7


# ── _split_into_chunks ───────────────────────────────────────────


class TestSplitIntoChunks:
    def test_short_text_single_chunk(self):
        text = "This is a short paragraph."
        chunks = _split_into_chunks(text, chunk_size=100, chunk_overlap=20)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_splits_at_paragraph_boundary(self):
        para1 = "First paragraph. " * 50   # ~200 tokens
        para2 = "Second paragraph. " * 50  # ~200 tokens
        text = f"{para1}\n\n{para2}"
        chunks = _split_into_chunks(text, chunk_size=250, chunk_overlap=20)
        assert len(chunks) >= 2

    def test_overlap_present(self):
        para1 = "Alpha beta gamma. " * 60
        para2 = "Delta epsilon zeta. " * 60
        text = f"{para1}\n\n{para2}"
        chunks = _split_into_chunks(text, chunk_size=200, chunk_overlap=50)
        assert len(chunks) >= 2
        # The tail of chunk 0 should appear at the start of chunk 1
        tail_0 = chunks[0][-50:]
        assert tail_0 in chunks[1] or chunks[1].startswith(tail_0[:20])

    def test_empty_text(self):
        assert _split_into_chunks("", chunk_size=100, chunk_overlap=20) == []
        assert _split_into_chunks("   \n\n  ", chunk_size=100, chunk_overlap=20) == []


# ── chunk_text ────────────────────────────────────────────────────


class TestChunkText:
    def _pages(self, texts: list[str]) -> list[PageContent]:
        return [PageContent(page_num=i + 1, text=t) for i, t in enumerate(texts)]

    def test_no_chapters_whole_doc(self):
        """Without chapters the entire document becomes one section."""
        pages = self._pages(["Page one text.\n" * 20])
        chunks = chunk_text(pages, [], chunk_size=50, chunk_overlap=10)
        assert len(chunks) >= 1
        assert all(c.chapter_no is None for c in chunks)

    def test_respects_chapter_boundaries(self):
        pages = self._pages([
            "Chapter 1: Intro\n" + ("Content. " * 80),
            "Chapter 2: More\n" + ("Stuff. " * 80),
        ])
        chapters = [
            ChapterInfo(chapter_no=1, title="Intro", page_start=1),
            ChapterInfo(chapter_no=2, title="More", page_start=2),
        ]
        chunks = chunk_text(pages, chapters, chunk_size=100, chunk_overlap=20)
        ch1 = [c for c in chunks if c.chapter_no == 1]
        ch2 = [c for c in chunks if c.chapter_no == 2]
        assert len(ch1) >= 1
        assert len(ch2) >= 1

    def test_chunk_index_is_sequential(self):
        pages = self._pages(["Text. " * 200])
        chunks = chunk_text(pages, [], chunk_size=100, chunk_overlap=20)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_token_count_within_bounds(self):
        """Each chunk should be ≤ chunk_size + some overlap tolerance."""
        pages = self._pages(["Paragraph of text. " * 300])
        chunks = chunk_text(pages, [], chunk_size=200, chunk_overlap=40)
        for c in chunks:
            # Allow 2× for overlap and boundary effects
            assert c.token_count <= 200 * 2, (
                f"chunk {c.chunk_index} has {c.token_count} tokens"
            )

    def test_page_markers(self):
        """Chunks should carry page-range information."""
        pages = self._pages([
            "Page one. " * 50,
            "Page two. " * 50,
        ])
        chunks = chunk_text(pages, [], chunk_size=100, chunk_overlap=10)
        assert all(c.page_start >= 1 for c in chunks)
        assert all(c.page_end <= 2 for c in chunks)
