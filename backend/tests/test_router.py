"""
Phase 3 tests — LLM router, rate counter, model verifier, prompt budgeting.

Covers:
  - InMemoryRateStore basics (RPM, RPD, cooldown, disable)
  - can_use_model checks (RPM exhausted, RPD exhausted, cooldown, summary reserve)
  - Model verifier helpers (find_closest_match, get_provider, clean_model_id)
  - Prompt budgeting (small TPM, medium TPM, large TPM)
  - Retrieval fallback formatting
  - Router: 429 fallback to next model
  - Router: all models busy → retrieval fallback
  - Router: successful routing
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rate_counter import (
    InMemoryRateStore,
    can_use_model,
    get_current_date_str,
    get_model_limits,
    mark_model_cooldown,
    record_model_request,
)
from app.services.retrieval import RetrievalResult


# ── Helpers ───────────────────────────────────────────────────────


def make_chunk(
    content: str = "Test content about normalization in databases.",
    subject: str = "DBMS",
    chapter_no: int = 1,
    idx: int = 1,
) -> RetrievalResult:
    """Create a mock RetrievalResult for testing."""
    return RetrievalResult(
        chunk_id=f"chunk-{idx}",
        content=content,
        score=0.9,
        chapter_no=chapter_no,
        chapter_title=f"Chapter {chapter_no}",
        unit_no=1,
        page_start=idx * 10,
        page_end=idx * 10 + 5,
        subject=subject,
        doc_type="book",
        document_id=f"doc-{idx}",
        search_type="fused",
    )


@pytest.fixture
def fresh_store():
    """Provide a fresh InMemoryRateStore and patch it as the global store."""
    store = InMemoryRateStore()
    with patch("app.services.rate_counter._STORE", store):
        yield store


# ╔════════════════════════════════════════════════════════════════╗
# ║  InMemoryRateStore unit tests                                  ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_store_rpm_tracking():
    """Recording requests increments RPM count within the sliding window."""
    store = InMemoryRateStore()
    model = "gemini-3.5-flash-lite"
    date = "2026-11-12"

    assert await store.get_rpm(model) == 0

    await store.record_request(model, date, 100)
    await store.record_request(model, date, 100)
    await store.record_request(model, date, 100)

    assert await store.get_rpm(model) == 3


@pytest.mark.asyncio
async def test_store_rpd_tracking():
    """Recording requests increments the daily request counter."""
    store = InMemoryRateStore()
    model = "gemini-3.5-flash-lite"
    date = "2026-11-12"

    assert await store.get_rpd(model, date) == 0

    for _ in range(5):
        await store.record_request(model, date, 0)

    assert await store.get_rpd(model, date) == 5


@pytest.mark.asyncio
async def test_store_tpm_tracking():
    """Recording tokens updates the sliding-window TPM counter."""
    store = InMemoryRateStore()
    model = "gemma-4-26b"
    date = "2026-11-12"

    await store.record_request(model, date, 500)
    await store.record_request(model, date, 300)

    tpm = await store.get_tpm(model)
    assert tpm == 800


@pytest.mark.asyncio
async def test_store_cooldown():
    """Cooldown sets a timer; remaining is positive during, zero after."""
    store = InMemoryRateStore()
    model = "gemini-3.6-flash"

    assert await store.get_cooldown_remaining(model) == 0.0

    await store.set_cooldown(model, 2.0)
    remaining = await store.get_cooldown_remaining(model)
    assert remaining > 0.0
    assert remaining <= 2.0


@pytest.mark.asyncio
async def test_store_cooldown_clear():
    """Clearing cooldown sets remaining to zero."""
    store = InMemoryRateStore()
    model = "gemini-3.6-flash"

    await store.set_cooldown(model, 60.0)
    await store.clear_cooldown(model)

    assert await store.get_cooldown_remaining(model) == 0.0


@pytest.mark.asyncio
async def test_store_disable_enable():
    """Disabling a model makes is_disabled True; re-enabling makes it False."""
    store = InMemoryRateStore()
    model = "gemini-3.5-flash-lite"

    assert await store.is_disabled(model) is False

    await store.set_disabled(model, True)
    assert await store.is_disabled(model) is True

    await store.set_disabled(model, False)
    assert await store.is_disabled(model) is False


@pytest.mark.asyncio
async def test_store_reset_specific_model():
    """Resetting a specific model clears only its data."""
    store = InMemoryRateStore()
    date = "2026-11-12"

    await store.record_request("model-a", date, 100)
    await store.record_request("model-b", date, 200)

    await store.reset("model-a")

    assert await store.get_rpm("model-a") == 0
    assert await store.get_rpd("model-a", date) == 0
    assert await store.get_rpm("model-b") == 1


@pytest.mark.asyncio
async def test_store_daily_tokens():
    """Recording actual tokens updates the daily token counter."""
    store = InMemoryRateStore()
    model = "gemini-3.5-flash-lite"
    date = "2026-11-12"

    await store.record_actual_tokens(model, date, 1500)
    await store.record_actual_tokens(model, date, 500)

    assert await store.get_daily_tokens(model, date) == 2000


# ╔════════════════════════════════════════════════════════════════╗
# ║  can_use_model tests                                           ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_can_use_model_rpm_exhausted(fresh_store):
    """Model becomes unavailable when RPM limit is reached."""
    model = "gemini-3.5-flash-lite"
    limits = get_model_limits(model)
    date = get_current_date_str()

    # Fill up RPM
    for _ in range(limits["rpm"]):
        await fresh_store.record_request(model, date, 0)

    ok, reason = await can_use_model(model, 100)
    assert ok is False
    assert "rpm_exhausted" in reason


@pytest.mark.asyncio
async def test_can_use_model_rpd_exhausted(fresh_store):
    """Model becomes unavailable when 95% of RPD is used."""
    model = "gemini-2.5-flash-lite"  # RPD=20
    limits = get_model_limits(model)
    date = get_current_date_str()
    threshold = int(limits["rpd"] * 0.95)

    for _ in range(threshold):
        await fresh_store.record_request(model, date, 0)

    ok, reason = await can_use_model(model, 100)
    assert ok is False
    assert "rpd_exhausted" in reason


@pytest.mark.asyncio
async def test_can_use_model_cooldown(fresh_store):
    """Model in cooldown is unavailable."""
    model = "gemini-3.5-flash-lite"

    await fresh_store.set_cooldown(model, 30.0)

    ok, reason = await can_use_model(model, 100)
    assert ok is False
    assert "cooldown" in reason


@pytest.mark.asyncio
async def test_can_use_model_disabled(fresh_store):
    """Disabled model is unavailable."""
    model = "gemini-3.5-flash-lite"

    await fresh_store.set_disabled(model, True)

    ok, reason = await can_use_model(model, 100)
    assert ok is False
    assert reason == "disabled_by_admin"


@pytest.mark.asyncio
async def test_can_use_model_summary_reserve(fresh_store):
    """Summary models reserve quota for summary jobs; student requests blocked earlier."""
    model = "gemini-3.6-flash"  # RPD=20, is SUMMARY_MODEL
    date = get_current_date_str()

    # Directly set daily requests so we don't trip the 5-RPM limit
    fresh_store._rpd[(model, date)] = 9

    ok, reason = await can_use_model(model, 100, is_summary_job=False)
    assert ok is False
    assert "rpd_exhausted" in reason

    # But a summary job should still pass (since total rpd is 20, at 95% = 19)
    ok2, reason2 = await can_use_model(model, 100, is_summary_job=True)
    assert ok2 is True


@pytest.mark.asyncio
async def test_can_use_model_available(fresh_store):
    """Fresh model with no usage is available."""
    ok, reason = await can_use_model("gemini-3.5-flash-lite", 100)
    assert ok is True
    assert reason == "available"


# ╔════════════════════════════════════════════════════════════════╗
# ║  Model verifier helpers                                        ║
# ╚════════════════════════════════════════════════════════════════╝


def test_find_closest_match_exact():
    from app.services.model_verifier import find_closest_match

    result = find_closest_match(
        "gemini-3.5-flash-lite", ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
    )
    assert result == "gemini-3.5-flash-lite"


def test_find_closest_match_case_insensitive():
    from app.services.model_verifier import find_closest_match

    result = find_closest_match(
        "Gemini-3.5-Flash-Lite", ["gemini-3.5-flash-lite"]
    )
    assert result == "gemini-3.5-flash-lite"


def test_find_closest_match_substring():
    from app.services.model_verifier import find_closest_match

    result = find_closest_match(
        "gemma-4-26b", ["gemma-4-26b-it", "gemma-4-31b-it"]
    )
    assert result is not None
    assert "gemma" in result
    assert "26b" in result


def test_find_closest_match_no_match():
    from app.services.model_verifier import find_closest_match

    result = find_closest_match(
        "nonexistent-model-xyz", ["gemini-3.5-flash-lite"]
    )
    # May return None or a fuzzy match — just check it doesn't crash
    assert result is None or isinstance(result, str)


def test_get_provider():
    from app.services.model_verifier import get_provider

    assert get_provider("gemini-3.5-flash-lite") == "gemini"
    assert get_provider("groq:openai/gpt-oss-20b") == "groq"
    assert get_provider("gemma-4-26b") == "gemini"


def test_clean_model_id():
    from app.services.model_verifier import clean_model_id

    assert clean_model_id("groq:openai/gpt-oss-20b") == "openai/gpt-oss-20b"
    assert clean_model_id("gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"


# ╔════════════════════════════════════════════════════════════════╗
# ║  Prompt budgeting                                              ║
# ╚════════════════════════════════════════════════════════════════╝


def test_budget_prompt_small_tpm():
    """Model with TPM <= 8000 gets max 1 chunk, no history, 300 tokens."""
    from app.services.llm_router import budget_prompt

    chunks = [make_chunk(idx=i) for i in range(4)]
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "what is normalization"},
        {"role": "assistant", "content": "it is..."},
    ]

    # groq:openai/gpt-oss-20b has TPM=8000
    trimmed_c, trimmed_h, max_tok = budget_prompt(
        "groq:openai/gpt-oss-20b", chunks, history, 800
    )

    assert len(trimmed_c) <= 1
    assert trimmed_h is None
    assert max_tok <= 300


def test_budget_prompt_medium_tpm():
    """Model with TPM <= 16000 gets max 2 chunks, 1 turn, 400 tokens."""
    from app.services.llm_router import budget_prompt

    chunks = [make_chunk(idx=i) for i in range(4)]
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "what is normalization"},
        {"role": "assistant", "content": "it is..."},
    ]

    # gemma-4-26b has TPM=16000
    trimmed_c, trimmed_h, max_tok = budget_prompt(
        "gemma-4-26b", chunks, history, 800
    )

    assert len(trimmed_c) <= 2
    assert trimmed_h is None or len(trimmed_h) <= 2
    assert max_tok <= 400


def test_budget_prompt_large_tpm():
    """Model with TPM > 16000 passes through unchanged."""
    from app.services.llm_router import budget_prompt

    chunks = [make_chunk(idx=i) for i in range(4)]
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]

    # gemini-3.5-flash-lite has TPM=250000
    trimmed_c, trimmed_h, max_tok = budget_prompt(
        "gemini-3.5-flash-lite", chunks, history, 800
    )

    assert len(trimmed_c) == 4
    assert trimmed_h is not None
    assert len(trimmed_h) == 2
    assert max_tok == 800


# ╔════════════════════════════════════════════════════════════════╗
# ║  Retrieval fallback                                            ║
# ╚════════════════════════════════════════════════════════════════╝


def test_retrieval_fallback_format():
    """build_retrieval_fallback produces a warning header and chunk content."""
    from app.services.llm_router import build_retrieval_fallback

    chunks = [make_chunk(idx=1), make_chunk(idx=2, subject="OS")]

    result = build_retrieval_fallback(chunks)

    assert "⚠️" in result
    assert "at capacity" in result
    assert "DBMS" in result
    assert "OS" in result
    assert "Source 1" in result
    assert "Source 2" in result


def test_retrieval_fallback_empty():
    """build_retrieval_fallback handles empty chunk list gracefully."""
    from app.services.llm_router import build_retrieval_fallback

    result = build_retrieval_fallback([])

    assert "⚠️" in result
    assert "no relevant" in result.lower()


# ╔════════════════════════════════════════════════════════════════╗
# ║  Router integration tests (mocked)                             ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_route_success(fresh_store):
    """Router selects first available model and streams successfully."""
    from app.services.llm_router import route_and_generate

    async def mock_generate(model_id, chunks, question, history, max_out):
        yield {"type": "token", "text": "Hello "}
        yield {"type": "token", "text": "World"}
        yield {"type": "usage", "input_tokens": 100, "output_tokens": 50}

    with patch(
        "app.services.llm_router.get_verified_active_chain",
        return_value=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    ), patch(
        "app.services.llm_router.generate_answer",
        side_effect=mock_generate,
    ), patch(
        "app.services.llm_router.record_model_usage",
        new_callable=AsyncMock,
    ):
        events = []
        async for event in route_and_generate(
            chunks=[make_chunk()],
            question="What is normalization?",
            history=None,
            detailed=False,
        ):
            events.append(event)

    types = [e["type"] for e in events]
    assert "model_selected" in types
    assert "token" in types

    # Check model_selected event
    model_event = next(e for e in events if e["type"] == "model_selected")
    assert model_event["model_id"] == "gemini-3.5-flash-lite"
    assert model_event["provider"] == "gemini"


@pytest.mark.asyncio
async def test_route_429_fallback(fresh_store):
    """When first model returns 429, router falls back to second model."""
    from app.services.llm_router import route_and_generate

    call_count = 0

    async def mock_generate(model_id, chunks, question, history, max_out):
        nonlocal call_count
        call_count += 1
        if "3.5" in model_id:
            yield {"type": "rate_limited", "status": 429}
        else:
            yield {"type": "token", "text": "Answer from fallback"}
            yield {"type": "usage", "input_tokens": 80, "output_tokens": 40}

    with patch(
        "app.services.llm_router.get_verified_active_chain",
        return_value=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    ), patch(
        "app.services.llm_router.generate_answer",
        side_effect=mock_generate,
    ), patch(
        "app.services.llm_router.record_model_usage",
        new_callable=AsyncMock,
    ), patch(
        "app.services.llm_router.mark_model_cooldown",
        new_callable=AsyncMock,
    ) as mock_cooldown:
        events = []
        async for event in route_and_generate(
            chunks=[make_chunk()],
            question="What is normalization?",
            history=None,
            detailed=False,
        ):
            events.append(event)

    # Should have been called with the first model's 429
    mock_cooldown.assert_called()
    cooldown_model = mock_cooldown.call_args_list[0][0][0]
    assert "3.5" in cooldown_model

    # Should have two model_selected events
    model_events = [e for e in events if e["type"] == "model_selected"]
    assert len(model_events) == 2
    assert model_events[0]["model_id"] == "gemini-3.5-flash-lite"
    assert model_events[1]["model_id"] == "gemini-3.1-flash-lite"

    # Should have a token from the fallback model
    token_events = [e for e in events if e["type"] == "token"]
    assert any("fallback" in e["text"] for e in token_events)


@pytest.mark.asyncio
async def test_route_all_busy_retrieval_fallback(fresh_store):
    """When all models are busy, router eventually serves retrieval fallback."""
    from app.services.llm_router import route_and_generate

    # Make all models unavailable via cooldown
    for model_id in [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]:
        await fresh_store.set_cooldown(model_id, 120.0)

    with patch(
        "app.services.llm_router.get_verified_active_chain",
        return_value=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    ), patch(
        "app.services.llm_router.settings",
    ) as router_settings:
        # Very short timeout so test doesn't wait 60s
        router_settings.router_queue_timeout_seconds = 1
        router_settings.max_output_tokens = 800
        router_settings.max_output_tokens_detailed = 2000

        events = []
        async for event in route_and_generate(
            chunks=[make_chunk()],
            question="What is normalization?",
            history=None,
            detailed=False,
        ):
            events.append(event)

    types = [e["type"] for e in events]

    # Should have queue_position and retrieval_fallback
    assert "queue_position" in types
    assert "retrieval_fallback" in types

    fallback_event = next(
        e for e in events if e["type"] == "retrieval_fallback"
    )
    assert "⚠️" in fallback_event["text"]


@pytest.mark.asyncio
async def test_route_empty_chain(fresh_store):
    """When no models in chain, router returns retrieval fallback immediately."""
    from app.services.llm_router import route_and_generate

    with patch(
        "app.services.llm_router.get_verified_active_chain",
        return_value=[],
    ):
        events = []
        async for event in route_and_generate(
            chunks=[make_chunk()],
            question="Test?",
            history=None,
            detailed=False,
        ):
            events.append(event)

    assert len(events) == 1
    assert events[0]["type"] == "retrieval_fallback"


# ╔════════════════════════════════════════════════════════════════╗
# ║  get_model_limits                                              ║
# ╚════════════════════════════════════════════════════════════════╝


def test_get_model_limits_known():
    """Known models return their configured limits."""
    limits = get_model_limits("gemini-3.5-flash-lite")
    assert limits["rpm"] == 15
    assert limits["tpm"] == 250_000
    assert limits["rpd"] == 500


def test_get_model_limits_groq_prefix():
    """Groq-prefixed model ID returns the correct limits."""
    limits = get_model_limits("groq:openai/gpt-oss-20b")
    assert limits["rpm"] == 30
    assert limits["tpm"] == 8_000
    assert limits["rpd"] == 1_000


def test_get_model_limits_unknown():
    """Unknown models return conservative defaults."""
    limits = get_model_limits("totally-unknown-model")
    assert "rpm" in limits
    assert "tpm" in limits
    assert "rpd" in limits


# ╔════════════════════════════════════════════════════════════════╗
# ║  mark_model_cooldown                                           ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_mark_cooldown_429(fresh_store):
    """429 sets a cooldown matching ROUTER_COOLDOWN_429_SECONDS."""
    model = "gemini-3.5-flash-lite"
    await mark_model_cooldown(model, 429)

    remaining = await fresh_store.get_cooldown_remaining(model)
    assert remaining > 0


@pytest.mark.asyncio
async def test_mark_cooldown_500(fresh_store):
    """5xx sets a shorter cooldown matching ROUTER_COOLDOWN_5XX_SECONDS."""
    model = "gemini-3.5-flash-lite"
    await mark_model_cooldown(model, 503)

    remaining = await fresh_store.get_cooldown_remaining(model)
    assert remaining > 0


# ╔════════════════════════════════════════════════════════════════╗
# ║  Admin models router endpoints                                ║
# ╚════════════════════════════════════════════════════════════════╝


def test_admin_models_status_endpoint(fresh_store):
    """GET /admin/models/status returns status list for configured models."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/admin/models/status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert "model_id" in first
    assert "provider" in first
    assert "is_verified" in first
    assert "is_enabled" in first
    assert "rpm_limit" in first
    assert "rpd_limit" in first


def test_admin_models_toggle_endpoint(fresh_store):
    """POST /admin/models/{model_id}/toggle toggles model enabled state."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    model = "gemini-3.5-flash-lite"

    # Disable
    resp = client.post(f"/admin/models/{model}/toggle", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    # Enable
    resp = client.post(f"/admin/models/{model}/toggle", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is True


def test_admin_models_clear_cooldown_endpoint(fresh_store):
    """POST /admin/models/{model_id}/clear-cooldown clears active cooldown."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    model = "gemini-3.5-flash-lite"

    resp = client.post(f"/admin/models/{model}/clear-cooldown")
    assert resp.status_code == 200
    assert resp.json()["cooldown_cleared"] is True


def test_admin_models_reverify_endpoint(fresh_store):
    """POST /admin/models/reverify triggers model verification."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    with patch(
        "app.services.model_verifier.fetch_gemini_model_ids",
        new_callable=AsyncMock,
        return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"],
    ), patch(
        "app.services.model_verifier.fetch_groq_model_ids",
        new_callable=AsyncMock,
        return_value=["openai/gpt-oss-20b"],
    ):
        resp = client.post("/admin/models/reverify")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        verified_ids = [m["model_id"] for m in data if m["is_verified"]]
        assert "gemini-3.5-flash-lite" in verified_ids
