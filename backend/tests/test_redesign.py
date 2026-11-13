"""
Unit and integration tests for the redesign:
1. Dual chains & API key isolation
2. Detailed detection (keywords + word count)
3. Response profiles by (plan, detailed)
4. Thinking mode conditions & reason codes
5. Thinking caps enforcement
6. Balance thresholds (thinking disabled < $2.00, paid retrieval-only < $0.75)
7. Per-model cost tracking (USD per 1M tokens)
8. Atomic units & thinking credits consumption and refund
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.config import (
    DEFAULT_MODEL_PRICES,
    DETAILED_KEYWORDS,
    DETAILED_WORD_THRESHOLD,
    RESPONSE_PROFILES,
    Settings,
    settings,
)
from app.routers.ask import detect_detailed
from app.services.quota import (
    check_thinking_conditions,
    compute_cost_usd,
    consume_quota,
    consume_thinking_credit,
    deduct_balance,
    get_account_balance,
    get_thinking_left_today,
    refund_quota,
    refund_thinking_credit,
    should_use_retrieval_only,
)
from app.services.llm_router import route_and_generate
from app.services.retrieval import RetrievalResult


def make_chunk(idx: int = 1, content: str = "Test lecture content.") -> RetrievalResult:
    return RetrievalResult(
        chunk_id=f"c-{idx}",
        content=content,
        score=0.85,
        chapter_no=1,
        chapter_title="Chapter 1",
        unit_no=1,
        page_start=1,
        page_end=3,
        subject="DBMS",
        doc_type="book",
        document_id=f"doc-{idx}",
        search_type="fused",
    )


# ╔════════════════════════════════════════════════════════════════╗
# ║  1. Dual chains & API key isolation                            ║
# ╚════════════════════════════════════════════════════════════════╝


def test_dual_chains_configured():
    s = Settings(
        GEMINI_API_KEY_FREE="free-key-123",
        GEMINI_API_KEY_PAID="paid-key-456",
        MODEL_CHAIN_FREE="gemini-3.5-flash-lite,gemma-4-26b",
        MODEL_CHAIN_PAID="gemini-3.5-flash-lite,groq:openai/gpt-oss-20b",
        MODEL_PREMIUM_THINKING="gemini-3.6-flash,gemini-3.8-flash",
    )
    assert s.gemini_api_key_free == "free-key-123"
    assert s.gemini_api_key_paid == "paid-key-456"
    assert s.model_chain_free_list == ["gemini-3.5-flash-lite", "gemma-4-26b"]
    assert s.model_chain_paid_list == ["gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b"]
    assert s.model_premium_thinking_list == ["gemini-3.6-flash", "gemini-3.8-flash"]


@pytest.mark.asyncio
async def test_router_key_isolation_free_vs_paid():
    """Free requests receive free key; paid requests receive paid key."""
    captured_keys = []

    async def mock_generate(model_id, chunks, question, history, max_out, **kwargs):
        captured_keys.append(kwargs.get("api_key"))
        yield {"type": "token", "text": "OK"}
        yield {"type": "usage", "input_tokens": 10, "output_tokens": 10}

    with patch("app.services.llm_router.generate_answer", side_effect=mock_generate), \
         patch("app.services.llm_router.get_verified_active_chain", return_value=["gemini-3.5-flash-lite"]), \
         patch("app.services.llm_router.get_verified_chain", return_value=["gemini-3.5-flash-lite"]), \
         patch("app.services.llm_router.record_model_usage", new_callable=AsyncMock):

        # Free request with free key
        async for _ in route_and_generate(
            chunks=[make_chunk()],
            question="What is SQL?",
            history=None,
            detailed=False,
            is_paid=False,
            api_key="FREE_KEY",
        ):
            pass

        assert captured_keys[-1] == "FREE_KEY"

        # Paid request with paid key
        async for _ in route_and_generate(
            chunks=[make_chunk()],
            question="What is SQL?",
            history=None,
            detailed=False,
            is_paid=True,
            api_key="PAID_KEY",
        ):
            pass

        assert captured_keys[-1] == "PAID_KEY"


# ╔════════════════════════════════════════════════════════════════╗
# ║  2. Detailed detection (keywords + word count)                 ║
# ╚════════════════════════════════════════════════════════════════╝


def test_detailed_detection_keywords():
    """Each keyword in DETAILED_KEYWORDS triggers detailed=True."""
    for kw in DETAILED_KEYWORDS:
        q = f"Can you explain B-trees {kw} please?"
        assert detect_detailed(q) is True, f"Failed to detect keyword '{kw}'"


def test_detailed_detection_word_count_threshold():
    """41 words triggers detailed; 40 words without keywords does not."""
    words_40 = "word " * 40
    words_41 = "word " * 41

    assert len(words_40.split()) == 40
    assert len(words_41.split()) == 41

    assert detect_detailed(words_40.strip()) is False
    assert detect_detailed(words_41.strip()) is True


def test_detailed_detection_short_normal():
    assert detect_detailed("What is a primary key?") is False
    assert detect_detailed("Define normal form.") is False


# ╔════════════════════════════════════════════════════════════════╗
# ║  3. Response profiles by (plan, detailed)                      ║
# ╚════════════════════════════════════════════════════════════════╝


def test_response_profiles_matrix():
    assert RESPONSE_PROFILES[("free", False)] == {"chunks": 3, "max_output": 600, "units": 1}
    assert RESPONSE_PROFILES[("free", True)]  == {"chunks": 5, "max_output": 1000, "units": 2}
    assert RESPONSE_PROFILES[("paid", False)] == {"chunks": 4, "max_output": 800, "units": 1}
    assert RESPONSE_PROFILES[("paid", True)]  == {"chunks": 6, "max_output": 2000, "units": 2}


# ╔════════════════════════════════════════════════════════════════╗
# ║  4. Thinking mode conditions & reason codes                    ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_thinking_conditions_disabled():
    with patch("app.services.quota.is_premium_enabled", AsyncMock(return_value=False)):
        ok, reason = await check_thinking_conditions("u1", {"is_paid": True})
        assert ok is False
        assert reason == "premium_disabled"


@pytest.mark.asyncio
async def test_thinking_conditions_not_paid():
    with patch("app.services.quota.is_premium_enabled", AsyncMock(return_value=True)):
        ok, reason = await check_thinking_conditions("u1", {"is_paid": False})
        assert ok is False
        assert reason == "not_paid"


@pytest.mark.asyncio
async def test_thinking_conditions_daily_credit_exhausted():
    with patch("app.services.quota.is_premium_enabled", AsyncMock(return_value=True)), \
         patch("app.services.quota.get_thinking_left_today", AsyncMock(return_value=0)):
        ok, reason = await check_thinking_conditions("u1", {"is_paid": True, "thinking_credits_per_day": 1})
        assert ok is False
        assert reason == "daily_limit_reached"


@pytest.mark.asyncio
async def test_thinking_conditions_daily_spend_cap_reached():
    with patch("app.services.quota.is_premium_enabled", AsyncMock(return_value=True)), \
         patch("app.services.quota.get_thinking_left_today", AsyncMock(return_value=1)), \
         patch("app.services.quota.get_today_premium_spend", AsyncMock(return_value=10.0)), \
         patch("app.services.quota.settings") as mock_settings:
        mock_settings.premium_daily_spend_cap_usd = 0.15
        ok, reason = await check_thinking_conditions("u1", {"is_paid": True, "thinking_credits_per_day": 1})
        assert ok is False
        assert reason == "daily_limit_reached"


@pytest.mark.asyncio
async def test_thinking_conditions_balance_low():
    with patch("app.services.quota.is_premium_enabled", AsyncMock(return_value=True)), \
         patch("app.services.quota.get_thinking_left_today", AsyncMock(return_value=1)), \
         patch("app.services.quota.get_today_premium_spend", AsyncMock(return_value=0.01)), \
         patch("app.services.quota.get_account_balance", AsyncMock(return_value=1.50)), \
         patch("app.services.quota.settings") as mock_settings:
        mock_settings.premium_daily_spend_cap_usd = 0.15
        mock_settings.premium_min_balance_usd = 2.0
        ok, reason = await check_thinking_conditions("u1", {"is_paid": True, "thinking_credits_per_day": 1})
        assert ok is False
        assert reason == "balance_low"


@pytest.mark.asyncio
async def test_thinking_conditions_all_pass():
    with patch("app.services.quota.is_premium_enabled", AsyncMock(return_value=True)), \
         patch("app.services.quota.get_thinking_left_today", AsyncMock(return_value=1)), \
         patch("app.services.quota.get_today_premium_spend", AsyncMock(return_value=0.02)), \
         patch("app.services.quota.get_account_balance", AsyncMock(return_value=5.00)), \
         patch("app.services.quota.settings") as mock_settings:
        mock_settings.premium_daily_spend_cap_usd = 0.15
        mock_settings.premium_min_balance_usd = 2.0
        ok, reason = await check_thinking_conditions("u1", {"is_paid": True, "thinking_credits_per_day": 1})
        assert ok is True
        assert reason == "ok"


# ╔════════════════════════════════════════════════════════════════╗
# ║  5. Thinking caps enforcement                                 ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_thinking_caps_applied():
    """In thinking mode, input tokens capped and output tokens use thinking_max_output_tokens."""
    captured_max_out = []
    captured_chunks = []

    async def mock_generate(model_id, chunks, question, history, max_out, **kwargs):
        captured_max_out.append(max_out)
        captured_chunks.append(len(chunks))
        yield {"type": "token", "text": "Thoughtful answer"}
        yield {"type": "usage", "input_tokens": 500, "output_tokens": 1000, "thinking_tokens": 500}

    # 10 large chunks that would exceed 8000 tokens
    many_chunks = [make_chunk(idx=i, content="A" * 4000) for i in range(10)]

    with patch("app.services.llm_router.generate_answer", side_effect=mock_generate), \
         patch("app.services.llm_router.get_verified_chain", return_value=["gemini-3.6-flash"]), \
         patch("app.services.llm_router.record_model_usage", new_callable=AsyncMock):

        async for _ in route_and_generate(
            chunks=many_chunks,
            question="Derive equation in detail",
            history=None,
            detailed=True,
            is_paid=True,
            thinking_mode=True,
            thinking_config={"thinkingBudget": 2000},
        ):
            pass

        assert len(captured_max_out) >= 1
        # Thinking mode uses settings.thinking_max_output_tokens (4000)
        assert captured_max_out[0] == settings.thinking_max_output_tokens
        # Chunks were trimmed to fit under 8000 input tokens
        assert captured_chunks[0] < 10


# ╔════════════════════════════════════════════════════════════════╗
# ║  6. Balance thresholds guard                                   ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_balance_guard_paid_user_retrieval_only():
    """When balance < PAID_MIN_BALANCE_USD (0.75), paid users switch to retrieval-only."""
    with patch("app.services.quota.get_account_balance", AsyncMock(return_value=0.50)):
        # Paid user
        retrieval_only = await should_use_retrieval_only(is_paid=True)
        assert retrieval_only is True

    with patch("app.services.quota.get_account_balance", AsyncMock(return_value=1.50)):
        # Above threshold
        retrieval_only = await should_use_retrieval_only(is_paid=True)
        assert retrieval_only is False


# ╔════════════════════════════════════════════════════════════════╗
# ║  7. Per-model cost tracking                                    ║
# ╚════════════════════════════════════════════════════════════════╝


def test_cost_computation_free_models():
    """Groq, Gemma, and zero-price models cost 0."""
    assert compute_cost_usd("gemma-4-26b", 1000, 500) == 0.0
    assert compute_cost_usd("gemma-4-31b", 1000, 500) == 0.0
    assert compute_cost_usd("groq:openai/gpt-oss-20b", 1000, 500) == 0.0


def test_cost_computation_gemini_models():
    """Gemini models priced accurately per 1M tokens."""
    # gemini-3.5-flash-lite: $0.30 input, $2.50 output per 1M
    cost = compute_cost_usd("gemini-3.5-flash-lite", 1_000_000, 1_000_000)
    assert cost == pytest.approx(2.80, rel=1e-3)

    # gemini-3.1-flash-lite: $0.25 input, $1.50 output per 1M
    cost = compute_cost_usd("gemini-3.1-flash-lite", 1_000_000, 1_000_000)
    assert cost == pytest.approx(1.75, rel=1e-3)

    # gemini-2.5-flash-lite: $0.10 input, $0.40 output per 1M
    cost = compute_cost_usd("gemini-2.5-flash-lite", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.50, rel=1e-3)


def test_cost_computation_thinking_tokens():
    """Thinking tokens count as output tokens."""
    # gemini-3.8-flash: $1.50 input, $7.50 output
    # 0 input, 1000 output, 1000 thinking -> 2000 output tokens
    cost_with_thinking = compute_cost_usd("gemini-3.8-flash", 0, 1000, thinking_tokens=1000)
    cost_double_output = compute_cost_usd("gemini-3.8-flash", 0, 2000, thinking_tokens=0)
    assert cost_with_thinking == cost_double_output
    assert cost_with_thinking == pytest.approx(0.015, rel=1e-3)


# ╔════════════════════════════════════════════════════════════════╗
# ║  8. Atomic units & thinking credits consumption and refund     ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.mark.asyncio
async def test_consume_quota_multi_units():
    mock_execute = AsyncMock(return_value="UPDATE 1")
    mock_fetchrow = AsyncMock(return_value={
        "requests_used": 1, "tokens_used": 500, "cache_hits": 0, "units_used": 2,
    })

    with patch("app.services.quota.execute", mock_execute), \
         patch("app.services.quota.fetchrow", mock_fetchrow):
        ok, usage = await consume_quota("user1", requests_limit=10, tokens_limit=40000, units=2)
        assert ok is True
        assert usage["units_used"] == 2


@pytest.mark.asyncio
async def test_refund_quota_multi_units():
    mock_execute = AsyncMock(return_value="UPDATE 1")
    with patch("app.services.quota.execute", mock_execute):
        await refund_quota("user1", units=2, tokens=100)
        assert mock_execute.called
        args = mock_execute.call_args[0]
        assert "GREATEST" in args[0]
        assert args[2] == 1  # requests
        assert args[3] == 2  # units


@pytest.mark.asyncio
async def test_thinking_credits_atomic_consume_and_refund():
    mock_execute = AsyncMock(return_value="UPDATE 1")
    mock_fetchrow = AsyncMock(return_value={"thinking_credits_used": 1})

    with patch("app.services.quota.execute", mock_execute), \
         patch("app.services.quota.fetchrow", mock_fetchrow):
        ok, used = await consume_thinking_credit("user1", daily_limit=1)
        assert ok is True
        assert used == 1

        # Second attempt should fail if limit is 1 and return None
        mock_fetchrow.return_value = None
        ok2, used2 = await consume_thinking_credit("user1", daily_limit=1)
        assert ok2 is False

        # Refund
        await refund_thinking_credit("user1")
        assert mock_execute.call_count >= 2
