"""
Tests for the /ask endpoint — special routes and LLM caller helpers.

Tests the pure-function helpers (citation building, context formatting,
message construction) without requiring a database or live LLM.
"""

import json
import pytest

from app.services.llm_caller import (
    SYSTEM_PROMPT,
    MODELS_WITHOUT_SYSTEM_ROLE,
    build_context_block,
    build_messages,
    get_provider,
)
from app.services.retrieval import RetrievalResult


# ╔════════════════════════════════════════════════════════════════╗
# ║  Fixtures                                                     ║
# ╚════════════════════════════════════════════════════════════════╝


def _make_chunk(
    content: str = "Test content",
    chapter_no: int = 1,
    subject: str = "DBMS",
    page_start: int = 10,
    page_end: int = 12,
) -> RetrievalResult:
    """Helper to create a test chunk."""
    return RetrievalResult(
        chunk_id="test-id",
        content=content,
        score=0.9,
        chapter_no=chapter_no,
        chapter_title="Normalization",
        unit_no=None,
        page_start=page_start,
        page_end=page_end,
        subject=subject,
        doc_type="book",
        document_id="doc-1",
        search_type="fused",
    )


# ╔════════════════════════════════════════════════════════════════╗
# ║  Provider detection                                           ║
# ╚════════════════════════════════════════════════════════════════╝


class TestGetProvider:
    def test_gemini_model(self):
        assert get_provider("gemini-3.5-flash-lite") == "gemini"

    def test_gemma_model(self):
        assert get_provider("gemma-4-26b") == "gemini"

    def test_groq_model(self):
        assert get_provider("groq:openai/gpt-oss-20b") == "groq"


# ╔════════════════════════════════════════════════════════════════╗
# ║  Context block formatting                                     ║
# ╚════════════════════════════════════════════════════════════════╝


class TestBuildContextBlock:
    def test_empty_chunks(self):
        result = build_context_block([])
        assert "No relevant context" in result

    def test_single_chunk(self):
        chunk = _make_chunk(content="Normalization is...")
        result = build_context_block([chunk])
        assert "Source 1" in result
        assert "DBMS" in result
        assert "Chapter 1" in result
        assert "Normalization is..." in result

    def test_multiple_chunks_numbered(self):
        c1 = _make_chunk(content="First")
        c2 = _make_chunk(content="Second", chapter_no=2, page_start=20)
        result = build_context_block([c1, c2])
        assert "Source 1" in result
        assert "Source 2" in result

    def test_page_range_in_header(self):
        chunk = _make_chunk(page_start=10, page_end=15)
        result = build_context_block([chunk])
        assert "10" in result
        assert "15" in result


# ╔════════════════════════════════════════════════════════════════╗
# ║  Message construction                                         ║
# ╚════════════════════════════════════════════════════════════════╝


class TestBuildMessages:
    def test_normal_model_has_system_role(self):
        chunk = _make_chunk()
        msgs = build_messages("what is normalization", [chunk],
                              model_id="gemini-3.5-flash-lite")
        assert msgs[0]["role"] == "system"
        assert SYSTEM_PROMPT in msgs[0]["content"]
        assert msgs[-1]["role"] == "user"

    def test_gemma_model_prepends_system_to_user(self):
        chunk = _make_chunk()
        msgs = build_messages("what is normalization", [chunk],
                              model_id="gemma-4-26b")
        # No system role for Gemma
        assert not any(m["role"] == "system" for m in msgs)
        # System prompt is in the user message
        assert SYSTEM_PROMPT in msgs[-1]["content"]

    def test_user_message_has_context_and_question(self):
        chunk = _make_chunk(content="NF explanation")
        msgs = build_messages("explain normalization", [chunk])
        user_msg = msgs[-1]["content"]
        assert "NF explanation" in user_msg
        assert "explain normalization" in user_msg

    def test_history_included(self):
        chunk = _make_chunk()
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        msgs = build_messages("next question", [chunk], history=history)
        roles = [m["role"] for m in msgs]
        # system, user (history), assistant (history), user (current)
        assert "assistant" in roles

    def test_history_limited_to_4_messages(self):
        chunk = _make_chunk()
        history = [
            {"role": "user", "content": f"q{i}"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"a{i}"}
            for i in range(10)
        ]
        msgs = build_messages("final", [chunk], history=history)
        # 1 system + 4 history + 1 current = 6
        assert len(msgs) == 6

    def test_no_history(self):
        chunk = _make_chunk()
        msgs = build_messages("test", [chunk])
        # 1 system + 1 user = 2
        assert len(msgs) == 2


# ╔════════════════════════════════════════════════════════════════╗
# ║  Citation building (from ask router)                          ║
# ╚════════════════════════════════════════════════════════════════╝


class TestCitationBuilding:
    def test_import_works(self):
        """Verify the ask router can be imported without errors."""
        from app.routers.ask import _build_citations
        assert callable(_build_citations)

    def test_builds_citations(self):
        from app.routers.ask import _build_citations
        chunks = [
            _make_chunk(subject="DBMS", chapter_no=1, page_start=10),
            _make_chunk(subject="DBMS", chapter_no=2, page_start=20),
        ]
        cits = _build_citations(chunks)
        assert len(cits) == 2
        assert cits[0]["subject"] == "DBMS"
        assert cits[0]["chapter_no"] == 1

    def test_deduplicates(self):
        from app.routers.ask import _build_citations
        c = _make_chunk(subject="DBMS", chapter_no=1, page_start=10)
        cits = _build_citations([c, c])
        assert len(cits) == 1
