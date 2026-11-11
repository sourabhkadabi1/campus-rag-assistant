"""
Document ingestion pipeline
  PDF → pages → chapter detection → chunking → embedding → pgvector storage

Pure-function helpers (detect_chapters, chunk_text, estimate_tokens) are
unit-testable without a database.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber

from app.config import settings
from app.database import execute, get_pool
from app.services.embeddings import get_embeddings_batch

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Data classes                                                 ║
# ╚════════════════════════════════════════════════════════════════╝


@dataclass
class PageContent:
    """Extracted content from one PDF page."""
    page_num: int           # 1-indexed
    text: str
    is_ocr: bool = False
    chars: list = field(default_factory=list)


@dataclass
class ChapterInfo:
    """A detected chapter / unit heading."""
    chapter_no: int
    title: str
    page_start: int         # 1-indexed
    heading_type: str = "chapter"   # chapter | unit | module


@dataclass
class TextChunk:
    """One chunk ready for embedding and DB storage."""
    content: str
    chapter_no: Optional[int]
    chapter_title: Optional[str]
    unit_no: Optional[int]
    page_start: int
    page_end: int
    chunk_index: int
    token_count: int


# ╔════════════════════════════════════════════════════════════════╗
# ║  Chapter detection patterns                                   ║
# ╚════════════════════════════════════════════════════════════════╝

CHAPTER_PATTERNS = [
    re.compile(r"^chapter\s+(\d+)\s*[:\-.]?\s*(.*)",  re.IGNORECASE),
    re.compile(r"^ch\.?\s*(\d+)\s*[:\-.]?\s*(.*)",    re.IGNORECASE),
    re.compile(r"^unit\s+(\d+)\s*[:\-.]?\s*(.*)",     re.IGNORECASE),
    re.compile(r"^module\s+(\d+)\s*[:\-.]?\s*(.*)",   re.IGNORECASE),
    re.compile(r"^part\s+(\d+)\s*[:\-.]?\s*(.*)",     re.IGNORECASE),
    re.compile(r"^(\d+)\.\s+(.+)",                     re.IGNORECASE),
]

# A heading's font must be at least this ratio × median body font
HEADING_FONT_RATIO = 1.3


# ╔════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                      ║
# ╚════════════════════════════════════════════════════════════════╝


def estimate_tokens(text: str) -> int:
    """Fast token estimate (~4 chars/token, matches GPT-class tokenisers)."""
    return max(1, len(text) // 4)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2 if n % 2 == 0 else s[n // 2]


def _line_font_size(chars: list, line_text: str) -> Optional[float]:
    """Dominant font size for the first ~30 characters of *line_text*."""
    if not chars or not line_text:
        return None
    prefix = line_text[:30]
    sizes = [c["size"] for c in chars
             if "text" in c and c["text"] in prefix and "size" in c]
    return _median(sizes) if sizes else None


# ╔════════════════════════════════════════════════════════════════╗
# ║  PDF text extraction                                          ║
# ╚════════════════════════════════════════════════════════════════╝


def extract_pages(pdf_path: str) -> list[PageContent]:
    """
    Extract text page-by-page with pdfplumber.
    Falls back to pytesseract OCR when a page yields < 50 chars.
    """
    pages: list[PageContent] = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            text = page.extract_text() or ""
            chars = page.chars if hasattr(page, "chars") else []
            is_ocr = False

            if len(text.strip()) < 50:
                ocr_text = _ocr_page(page, pdf_path, page_num)
                if ocr_text and len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    is_ocr = True

            pages.append(PageContent(page_num=page_num, text=text,
                                     is_ocr=is_ocr, chars=chars))

    return pages


def _ocr_page(page, pdf_path: str, page_num: int) -> str:
    """OCR a single page via pytesseract. Returns empty string on failure."""
    try:
        import pytesseract  # type: ignore
        img = page.to_image(resolution=300)
        return pytesseract.image_to_string(img.original)
    except Exception as exc:
        logger.warning("OCR failed for page %d of %s: %s", page_num, pdf_path, exc)
        return ""


# ╔════════════════════════════════════════════════════════════════╗
# ║  Chapter / heading detection                                  ║
# ╚════════════════════════════════════════════════════════════════╝


def detect_chapters(pages: list[PageContent]) -> list[ChapterInfo]:
    """
    Detect chapter / unit headings using regex + font-size heuristics.
    Returns deduplicated chapters sorted by page_start.
    """
    # Median font size across the whole document
    all_sizes = [c["size"] for p in pages for c in p.chars if "size" in c]
    median_fs = _median(all_sizes) if all_sizes else 12.0

    chapters: list[ChapterInfo] = []

    for page in pages:
        for line in page.text.split("\n"):
            stripped = line.strip()
            if not stripped or len(stripped) > 200:
                continue

            for pattern in CHAPTER_PATTERNS:
                m = pattern.match(stripped)
                if not m:
                    continue

                chapter_no = int(m.group(1))
                title = (m.group(2) or "").strip().rstrip(":.—-")

                heading_type = "chapter"
                if "unit" in pattern.pattern.lower():
                    heading_type = "unit"
                elif "module" in pattern.pattern.lower():
                    heading_type = "module"

                # Font-size gate: reject lines that look like body text
                if page.chars and all_sizes:
                    fs = _line_font_size(page.chars, stripped)
                    if fs and fs < median_fs * HEADING_FONT_RATIO and len(stripped) > 80:
                        break  # not a real heading

                chapters.append(ChapterInfo(
                    chapter_no=chapter_no,
                    title=title,
                    page_start=page.page_num,
                    heading_type=heading_type,
                ))
                break  # first matching pattern wins

    # Deduplicate by (heading_type, chapter_no), keep first
    seen: set[tuple[str, int]] = set()
    unique: list[ChapterInfo] = []
    for ch in chapters:
        key = (ch.heading_type, ch.chapter_no)
        if key not in seen:
            seen.add(key)
            unique.append(ch)

    return sorted(unique, key=lambda c: c.page_start)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Chunking                                                     ║
# ╚════════════════════════════════════════════════════════════════╝


def _build_chapter_ranges(
    chapters: list[ChapterInfo], total_pages: int
) -> list[tuple[Optional[int], Optional[str], Optional[str], int, int]]:
    """(chapter_no, title, heading_type, page_start, page_end) per chapter."""
    if not chapters:
        return []

    ranges = []

    # Preamble before the first detected chapter
    if chapters[0].page_start > 1:
        ranges.append((None, None, None, 1, chapters[0].page_start - 1))

    for i, ch in enumerate(chapters):
        end = chapters[i + 1].page_start - 1 if i + 1 < len(chapters) else total_pages
        ranges.append((ch.chapter_no, ch.title, ch.heading_type,
                        ch.page_start, max(ch.page_start, end)))

    return ranges


def _get_overlap_text(text: str, overlap_tokens: int) -> str:
    """Return the tail of *text* worth ~overlap_tokens tokens."""
    target = overlap_tokens * 4
    return text[-target:] if len(text) > target else text


def _split_into_chunks(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """
    Split *text* into chunks of ~chunk_size tokens with overlap.
    Breaks at paragraph → sentence boundaries.
    Attempts to keep tables / code blocks intact.
    """
    if estimate_tokens(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""
    current_tok = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        ptok = estimate_tokens(para)

        if ptok > chunk_size:
            # Flush what we have
            if current.strip():
                chunks.append(current.strip())
                current = _get_overlap_text(current, chunk_overlap)
                current_tok = estimate_tokens(current)

            # Split the oversized paragraph by sentences
            for sent in re.split(r"(?<=[.!?])\s+", para):
                stok = estimate_tokens(sent)
                if current_tok + stok > chunk_size and current.strip():
                    chunks.append(current.strip())
                    current = _get_overlap_text(current, chunk_overlap) + " " + sent
                    current_tok = estimate_tokens(current)
                else:
                    current += " " + sent
                    current_tok += stok

        elif current_tok + ptok > chunk_size:
            if current.strip():
                chunks.append(current.strip())
                current = _get_overlap_text(current, chunk_overlap) + "\n\n" + para
                current_tok = estimate_tokens(current)
            else:
                current = para
                current_tok = ptok
        else:
            current += "\n\n" + para
            current_tok += ptok

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _find_chunk_pages(chunk_text: str, fallback_start: int, fallback_end: int) -> tuple[int, int]:
    """Extract page range from [Page N] markers embedded in the text."""
    found = re.findall(r"\[Page (\d+)\]", chunk_text)
    if found:
        nums = [int(p) for p in found]
        return min(nums), max(nums)
    return fallback_start, fallback_end


def chunk_text(
    pages: list[PageContent],
    chapters: list[ChapterInfo],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> list[TextChunk]:
    """
    Chunk the full document, respecting chapter boundaries.
    Returns ordered TextChunk objects ready for embedding.
    """
    chunk_size = chunk_size or settings.chunk_size_tokens
    chunk_overlap = chunk_overlap or settings.chunk_overlap_tokens

    chapter_ranges = _build_chapter_ranges(chapters, len(pages))
    if not chapter_ranges:
        chapter_ranges = [(None, None, None, 1, len(pages))]

    all_chunks: list[TextChunk] = []
    idx = 0

    for ch_no, ch_title, h_type, pg_start, pg_end in chapter_ranges:
        section = ""
        for p in pages:
            if pg_start <= p.page_num <= pg_end:
                section += f"\n[Page {p.page_num}]\n{p.text}"

        if not section.strip():
            continue

        unit_no = ch_no if h_type in ("unit", "module") else None

        for raw in _split_into_chunks(section, chunk_size, chunk_overlap):
            ps, pe = _find_chunk_pages(raw, pg_start, pg_end)
            all_chunks.append(TextChunk(
                content=raw,
                chapter_no=ch_no,
                chapter_title=ch_title,
                unit_no=unit_no,
                page_start=ps,
                page_end=pe,
                chunk_index=idx,
                token_count=estimate_tokens(raw),
            ))
            idx += 1

    return all_chunks


# ╔════════════════════════════════════════════════════════════════╗
# ║  Full ingestion pipeline (background task)                    ║
# ╚════════════════════════════════════════════════════════════════╝


async def ingest_document(
    document_id: str, pdf_path: str, metadata: dict
) -> None:
    """
    End-to-end ingestion.  Called as a FastAPI BackgroundTask.
    Updates document.ingestion_status throughout.
    """
    from app.services.summarizer import generate_chapter_summaries

    try:
        await execute(
            """UPDATE documents
               SET ingestion_status = 'processing',
                   ingestion_started_at = NOW(), updated_at = NOW()
               WHERE id = $1""",
            document_id,
        )

        # 1. Extract pages
        pages = extract_pages(pdf_path)
        total_pages = len(pages)
        await execute(
            "UPDATE documents SET total_pages=$1, updated_at=NOW() WHERE id=$2",
            total_pages, document_id,
        )
        logger.info("doc %s: extracted %d pages", document_id, total_pages)

        # 2. Detect chapters
        chapters = detect_chapters(pages)
        logger.info("doc %s: detected %d chapters", document_id, len(chapters))

        # 3. Chunk
        chunks = chunk_text(pages, chapters)
        logger.info("doc %s: created %d chunks", document_id, len(chunks))

        if not chunks:
            await execute(
                """UPDATE documents
                   SET ingestion_status='failed',
                       ingestion_error='No text content extracted',
                       ingestion_completed_at=NOW(), updated_at=NOW()
                   WHERE id=$1""",
                document_id,
            )
            return

        # 4. Embed (batched)
        embeddings = get_embeddings_batch([c.content for c in chunks])
        logger.info("doc %s: generated %d embeddings", document_id, len(embeddings))

        # 5. Store in DB
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Remove previous chunks for re-uploads
            await conn.execute("DELETE FROM chunks WHERE document_id=$1", document_id)

            for chunk, emb in zip(chunks, embeddings):
                emb_str = "[" + ",".join(str(v) for v in emb) + "]"
                await conn.execute(
                    """INSERT INTO chunks
                       (id, document_id, content, embedding,
                        semester, department, subject, academic_year, doc_type,
                        chapter_no, chapter_title, unit_no,
                        page_start, page_end, chunk_index, token_count)
                       VALUES ($1,$2,$3,$4::vector,
                               $5,$6,$7,$8,$9,
                               $10,$11,$12,$13,$14,$15,$16)""",
                    str(uuid.uuid4()), document_id, chunk.content, emb_str,
                    metadata["semester"], metadata["department"],
                    metadata["subject"], metadata["academic_year"],
                    metadata["doc_type"],
                    chunk.chapter_no, chunk.chapter_title, chunk.unit_no,
                    chunk.page_start, chunk.page_end,
                    chunk.chunk_index, chunk.token_count,
                )

        logger.info("doc %s: stored %d chunks", document_id, len(chunks))

        # 6. Generate chapter summaries
        if chapters:
            chapter_data = []
            for ch in chapters:
                text = "\n\n".join(
                    c.content for c in chunks if c.chapter_no == ch.chapter_no
                )
                if text.strip():
                    chapter_data.append({
                        "chapter_no": ch.chapter_no,
                        "title": ch.title,
                        "text": text,
                    })
            if chapter_data:
                await generate_chapter_summaries(document_id, chapter_data)

        # Done
        await execute(
            """UPDATE documents
               SET ingestion_status='done',
                   ingestion_completed_at=NOW(), updated_at=NOW()
               WHERE id=$1""",
            document_id,
        )
        logger.info("doc %s: ingestion complete", document_id)

    except Exception as exc:
        logger.exception("doc %s: ingestion failed: %s", document_id, exc)
        try:
            await execute(
                """UPDATE documents
                   SET ingestion_status='failed', ingestion_error=$1,
                       ingestion_completed_at=NOW(), updated_at=NOW()
                   WHERE id=$2""",
                str(exc)[:2000], document_id,
            )
        except Exception:
            logger.exception("Could not record ingestion failure for %s", document_id)
