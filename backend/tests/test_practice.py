"""
Tests for Stage 7: Practice & Quiz Generation.

Covers:
- JSON cleanup and prompt builder
- Plan feature gate (free users blocked, paid users allowed)
- Atomic quota consumption (2 units) and refund on failure
- Quiz generation and response structure
- Quiz answer submission, automatic MCQ scoring, and feedback
- Router endpoints: /practice/generate, /practice/submit, /practice/history, /practice/{id}
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    PracticeDifficulty,
    PracticeGenerateRequest,
    PracticeQuestionType,
    PracticeSubmitRequest,
)
from app.services.practice_generator import (
    _build_practice_prompt,
    _clean_json_text,
    generate_practice_set,
    submit_practice_answers,
)
from app.services.retrieval import RetrievalResult


# ── 1. Unit Tests for Helpers ─────────────────────────────────────


def test_clean_json_text_direct():
    raw = '{"questions": [{"id": "q1", "question": "What is TCP?"}]}'
    assert _clean_json_text(raw) == raw


def test_clean_json_text_markdown_block():
    raw = """```json
{"questions": [{"id": "q1", "question": "What is UDP?"}]}
```"""
    cleaned = _clean_json_text(raw)
    assert json.loads(cleaned)["questions"][0]["question"] == "What is UDP?"


def test_clean_json_text_chatter():
    raw = """Here is your practice quiz:
{"questions": [{"id": "q1", "question": "Explain OSI."}]}
Hope this helps!"""
    cleaned = _clean_json_text(raw)
    data = json.loads(cleaned)
    assert data["questions"][0]["question"] == "Explain OSI."


def test_build_practice_prompt():
    chunks = [
        RetrievalResult(
            chunk_id="c1",
            content="Transport layer provides logical communication.",
            score=0.9,
            chapter_no=3,
            chapter_title="Transport Layer",
            unit_no=2,
            page_start=150,
            page_end=152,
            subject="Computer Networks",
            doc_type="book",
            document_id="doc-123",
            search_type="vector",
        )
    ]
    prompt = _build_practice_prompt(
        subject="Computer Networks",
        semester=3,
        department="CSE",
        chunks=chunks,
        question_type=PracticeQuestionType.MCQ,
        difficulty=PracticeDifficulty.MEDIUM,
        count=3,
        topic="Transport Layer Services",
        chapter_no=3,
        unit_no=2,
    )
    assert "Computer Networks" in prompt
    assert "Transport Layer Services" in prompt
    assert "Transport layer provides logical communication" in prompt
    assert "REQUIRED JSON FORMAT" in prompt


# ── 2. Service-Level Tests with Mocks ─────────────────────────────


@pytest.mark.asyncio
async def test_generate_practice_set_free_user_blocked():
    """Free user without quiz_generation feature gets blocked."""
    with patch("app.services.practice_generator.get_user_plan", new_callable=AsyncMock) as mock_plan:
        mock_plan.return_value = {
            "plan_name": "free",
            "is_paid": False,
            "features": {"quiz_generation": False},
            "requests_per_day": 10,
            "tokens_per_day": 40000,
        }

        req = PracticeGenerateRequest(
            subject="Computer Networks",
            question_type=PracticeQuestionType.MCQ,
            count=3,
        )

        with pytest.raises(ValueError, match="Premium feature"):
            await generate_practice_set("user-free", 3, "CSE", req)


@pytest.mark.asyncio
async def test_generate_practice_set_quota_exceeded():
    """User over quota gets rejected."""
    with patch("app.services.practice_generator.get_user_plan", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.practice_generator.consume_quota", new_callable=AsyncMock) as mock_consume:
        mock_plan.return_value = {
            "plan_name": "paid",
            "is_paid": True,
            "features": {"quiz_generation": True},
            "requests_per_day": 30,
            "tokens_per_day": 100000,
        }
        mock_consume.return_value = (False, {})

        req = PracticeGenerateRequest(
            subject="Computer Networks",
            question_type=PracticeQuestionType.MCQ,
            count=3,
        )

        with pytest.raises(ValueError, match="quota exceeded"):
            await generate_practice_set("user-paid", 3, "CSE", req)


@pytest.mark.asyncio
async def test_generate_practice_set_no_materials_refunds_quota():
    """If no chunks found, refund 2 units and raise informative error."""
    with patch("app.services.practice_generator.get_user_plan", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.practice_generator.consume_quota", new_callable=AsyncMock) as mock_consume, \
         patch("app.services.practice_generator.hybrid_search", new_callable=AsyncMock) as mock_search, \
         patch("app.services.practice_generator.refund_quota", new_callable=AsyncMock) as mock_refund:

        mock_plan.return_value = {
            "plan_name": "paid",
            "is_paid": True,
            "features": {"quiz_generation": True},
            "requests_per_day": 30,
            "tokens_per_day": 100000,
        }
        mock_consume.return_value = (True, {})
        mock_search.return_value = ([], None)

        req = PracticeGenerateRequest(
            subject="NonExistentSubject",
            question_type=PracticeQuestionType.MCQ,
            count=3,
        )

        with pytest.raises(ValueError, match="No course material found"):
            await generate_practice_set("user-paid", 3, "CSE", req)

        mock_refund.assert_called_once_with("user-paid", units=2)


@pytest.mark.asyncio
async def test_generate_practice_set_success():
    """Successful practice quiz generation."""
    sample_chunk = RetrievalResult(
        chunk_id="c1",
        content="Subnetting divides a larger network into smaller subnetworks.",
        score=0.88,
        chapter_no=4,
        chapter_title="Network Layer",
        unit_no=3,
        page_start=210,
        page_end=215,
        subject="Computer Networks",
        doc_type="book",
        document_id="doc-456",
        search_type="vector",
    )

    llm_output = json.dumps({
        "questions": [
            {
                "id": "q1",
                "type": "mcq",
                "question": "What is the primary purpose of subnetting?",
                "options": [
                    "A) To divide a network into smaller subnetworks",
                    "B) To increase collision domains",
                    "C) To convert digital signals to analog",
                    "D) To encrypt packet headers"
                ],
                "correct_option_index": 0,
                "model_answer": "Subnetting divides a network into smaller address spaces for efficient routing.",
                "key_points": ["Address conservation", "Routing efficiency"],
                "citation": {
                    "chapter_no": 4,
                    "chapter_title": "Network Layer",
                    "page_start": 210,
                    "page_end": 215
                }
            }
        ]
    })

    async def fake_generator(*args, **kwargs):
        yield {"type": "model_selected", "model_id": "gemini-3.5-flash-lite"}
        yield {"type": "token", "text": llm_output}
        yield {"type": "usage", "input_tokens": 300, "output_tokens": 120}

    with patch("app.services.practice_generator.get_user_plan", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.practice_generator.consume_quota", new_callable=AsyncMock) as mock_consume, \
         patch("app.services.practice_generator.hybrid_search", new_callable=AsyncMock) as mock_search, \
         patch("app.services.practice_generator.route_and_generate", side_effect=fake_generator), \
         patch("app.services.practice_generator.record_tokens", new_callable=AsyncMock), \
         patch("app.services.practice_generator.execute", new_callable=AsyncMock):

        mock_plan.return_value = {
            "plan_name": "paid",
            "is_paid": True,
            "features": {"quiz_generation": True},
            "requests_per_day": 30,
            "tokens_per_day": 100000,
        }
        mock_consume.return_value = (True, {})
        mock_search.return_value = ([sample_chunk], None)

        req = PracticeGenerateRequest(
            subject="Computer Networks",
            question_type=PracticeQuestionType.MCQ,
            count=1,
        )

        res = await generate_practice_set("user-paid", 3, "CSE", req)
        assert res.subject == "Computer Networks"
        assert res.units_charged == 2
        assert len(res.questions) == 1
        q = res.questions[0]
        assert q.id == "q1"
        assert q.correct_option_index == 0
        assert len(q.options) == 4
        assert q.citation.chapter_no == 4


@pytest.mark.asyncio
async def test_submit_practice_answers():
    """Scoring calculation on practice submissions."""
    db_quiz_record = {
        "id": "quiz-1",
        "user_id": "user-paid",
        "questions": json.dumps([
            {
                "id": "q1",
                "type": "mcq",
                "question": "Question 1?",
                "options": ["A", "B", "C", "D"],
                "correct_option_index": 1,
                "model_answer": "B is correct.",
            },
            {
                "id": "q2",
                "type": "mcq",
                "question": "Question 2?",
                "options": ["A", "B", "C", "D"],
                "correct_option_index": 3,
                "model_answer": "D is correct.",
            }
        ])
    }

    with patch("app.services.practice_generator.fetchrow", new_callable=AsyncMock) as mock_fetch, \
         patch("app.services.practice_generator.execute", new_callable=AsyncMock) as mock_exec:
        mock_fetch.return_value = db_quiz_record

        # Submit 1 correct, 1 wrong
        submit_req = PracticeSubmitRequest(
            practice_set_id="quiz-1",
            answers={"q1": 1, "q2": 0},
        )
        sub_res = await submit_practice_answers("user-paid", submit_req)
        assert sub_res.score == 1
        assert sub_res.total == 2
        assert sub_res.percentage == 50.0
        assert sub_res.feedback[0]["is_correct"] is True
        assert sub_res.feedback[1]["is_correct"] is False


# ── 3. Router Integration Tests ───────────────────────────────────


def test_router_generate_quiz_unauthorized_missing_user_id():
    """Missing X-User-Id returns HTTP 400."""
    client = TestClient(app)
    resp = client.post("/practice/generate", json={"subject": "Computer Networks"})
    assert resp.status_code == 400
    assert "Missing X-User-Id" in resp.json()["detail"]


def test_router_generate_quiz_forbidden_free_plan():
    """Free user gets HTTP 403."""
    client = TestClient(app)
    with patch("app.routers.practice.get_server_profile", new_callable=AsyncMock) as mock_prof, \
         patch("app.services.practice_generator.get_user_plan", new_callable=AsyncMock) as mock_plan:
        mock_prof.return_value = {"semester": 3, "department": "CSE"}
        mock_plan.return_value = {
            "plan_name": "free",
            "is_paid": False,
            "features": {"quiz_generation": False},
            "requests_per_day": 10,
            "tokens_per_day": 40000,
        }
        resp = client.post(
            "/practice/generate",
            headers={"X-User-Id": "free-user-uuid"},
            json={"subject": "Computer Networks"},
        )
        assert resp.status_code == 403
        assert "Premium feature" in resp.json()["detail"]


def test_router_submit_quiz_missing_user():
    """Missing X-User-Id on submit returns 400."""
    client = TestClient(app)
    resp = client.post("/practice/submit", json={"practice_set_id": "xyz", "answers": {}})
    assert resp.status_code == 400


def test_router_get_history():
    """GET /practice/history returns list of historical quizzes."""
    client = TestClient(app)
    with patch("app.routers.practice.list_user_practice_sets", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [
            {"id": "p1", "subject": "Networks", "question_count": 5}
        ]
        resp = client.get("/practice/history", headers={"X-User-Id": "user-uuid"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["subject"] == "Networks"

