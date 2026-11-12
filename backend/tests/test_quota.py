"""
Tests for Phase 4 — Quota enforcement, budget guard, per-user rate limiting.

Covers:
  - Atomic quota consume / refund logic
  - Concurrent requests cannot exceed the limit
  - Token tracking and blocking
  - Cache hits not consuming quota
  - Budget guard activation for free vs paid users
  - Per-user per-minute abuse rate limiter
  - Plan lookup and expiry fallback
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ╔════════════════════════════════════════════════════════════════╗
# ║  Per-user rate limiter tests (no DB needed)                   ║
# ╚════════════════════════════════════════════════════════════════╝


class TestUserRateLimiter:
    """Test the in-memory per-user per-minute rate limiter."""

    def setup_method(self):
        from app.services.abuse import UserRateLimiter
        self.limiter = UserRateLimiter()

    def test_allows_under_limit(self):
        ok, count = self.limiter.check_and_record("user1", limit=5)
        assert ok is True
        assert count == 1

    def test_blocks_at_limit(self):
        for _ in range(5):
            self.limiter.check_and_record("user1", limit=5)

        ok, count = self.limiter.check_and_record("user1", limit=5)
        assert ok is False
        assert count == 5

    def test_different_users_independent(self):
        for _ in range(5):
            self.limiter.check_and_record("user1", limit=5)

        ok, _ = self.limiter.check_and_record("user2", limit=5)
        assert ok is True

    def test_sliding_window_expiry(self):
        """After 60s the window should have expired."""
        self.limiter._requests["user1"] = [time.time() - 61.0] * 5
        ok, count = self.limiter.check_and_record("user1", limit=5)
        assert ok is True
        assert count == 1

    def test_get_count(self):
        self.limiter.check_and_record("user1", limit=10)
        self.limiter.check_and_record("user1", limit=10)
        assert self.limiter.get_count("user1") == 2

    def test_reset_specific_user(self):
        self.limiter.check_and_record("user1", limit=10)
        self.limiter.check_and_record("user2", limit=10)
        self.limiter.reset("user1")
        assert self.limiter.get_count("user1") == 0
        assert self.limiter.get_count("user2") == 1

    def test_reset_all(self):
        self.limiter.check_and_record("user1", limit=10)
        self.limiter.check_and_record("user2", limit=10)
        self.limiter.reset()
        assert self.limiter.get_count("user1") == 0
        assert self.limiter.get_count("user2") == 0


# ╔════════════════════════════════════════════════════════════════╗
# ║  Bot protection helper tests                                  ║
# ╚════════════════════════════════════════════════════════════════╝


class TestBotProtection:
    def test_honeypot_empty_is_human(self):
        from app.services.abuse import check_honeypot
        assert check_honeypot("") is True
        assert check_honeypot(None) is True

    def test_honeypot_filled_is_bot(self):
        from app.services.abuse import check_honeypot
        assert check_honeypot("spambot") is False

    def test_timing_fast_is_bot(self):
        from app.services.abuse import check_timing
        assert check_timing(time.time() - 0.5) is False

    def test_timing_normal_is_human(self):
        from app.services.abuse import check_timing
        assert check_timing(time.time() - 5.0) is True

    def test_timing_none_is_allowed(self):
        from app.services.abuse import check_timing
        assert check_timing(None) is True


# ╔════════════════════════════════════════════════════════════════╗
# ║  Quota consume / refund tests (mocked DB)                    ║
# ╚════════════════════════════════════════════════════════════════╝


class TestQuotaConsume:
    """Test atomic quota consume logic with mocked database calls."""

    @pytest.fixture(autouse=True)
    def _patch_db(self):
        """Patch all database functions used by quota module."""
        self.mock_execute = AsyncMock(return_value="UPDATE 1")
        self.mock_fetchrow = AsyncMock()
        self.mock_fetchval = AsyncMock()

        with patch("app.services.quota.execute", self.mock_execute), \
             patch("app.services.quota.fetchrow", self.mock_fetchrow), \
             patch("app.services.quota.fetchval", self.mock_fetchval), \
             patch("app.services.quota.fetch", AsyncMock(return_value=[])):
            yield

    @pytest.mark.asyncio
    async def test_consume_success(self):
        """Consuming quota returns True and updated usage."""
        from app.services.quota import consume_quota

        # Mock: row exists after upsert, update succeeds
        self.mock_fetchrow.return_value = {
            "requests_used": 1, "tokens_used": 0, "cache_hits": 0,
        }

        ok, usage = await consume_quota("user1", 10, 40000)
        assert ok is True
        assert usage["requests_used"] == 1

    @pytest.mark.asyncio
    async def test_consume_requests_exceeded(self):
        """Returns False when request limit is reached."""
        from app.services.quota import consume_quota

        # First call (upsert) returns None, second call (update) returns None
        # meaning the WHERE clause didn't match
        self.mock_fetchrow.side_effect = [
            None,  # UPDATE returns no rows (quota exceeded)
            {"requests_used": 10, "tokens_used": 5000, "cache_hits": 3},  # SELECT
        ]

        ok, usage = await consume_quota("user1", 10, 40000)
        assert ok is False
        assert usage["reason"] == "requests_exceeded"
        assert usage["requests_used"] == 10

    @pytest.mark.asyncio
    async def test_consume_tokens_exceeded(self):
        """Returns False when token limit is reached (and refunds request)."""
        from app.services.quota import consume_quota

        # UPDATE succeeds but tokens_used >= tokens_limit
        self.mock_fetchrow.return_value = {
            "requests_used": 5, "tokens_used": 40000, "cache_hits": 2,
        }

        ok, usage = await consume_quota("user1", 10, 40000)
        assert ok is False
        assert usage["reason"] == "tokens_exceeded"
        # Should have called execute to refund
        refund_calls = [
            c for c in self.mock_execute.call_args_list
            if "GREATEST" in str(c)
        ]
        assert len(refund_calls) >= 1

    @pytest.mark.asyncio
    async def test_refund_quota(self):
        """Refund decrements counters."""
        from app.services.quota import refund_quota

        await refund_quota("user1", requests=1, tokens=500)

        # Should have called execute with GREATEST(0, ...)
        calls = [str(c) for c in self.mock_execute.call_args_list]
        assert any("GREATEST" in c for c in calls)


class TestQuotaRemaining:
    """Test get_remaining returns correct values."""

    @pytest.fixture(autouse=True)
    def _patch(self):
        self.mock_fetchrow = AsyncMock()
        self.mock_fetchval = AsyncMock()

        with patch("app.services.quota.execute", AsyncMock()), \
             patch("app.services.quota.fetchrow", self.mock_fetchrow), \
             patch("app.services.quota.fetchval", self.mock_fetchval), \
             patch("app.services.quota.fetch", AsyncMock(return_value=[])), \
             patch("app.services.quota.should_use_retrieval_only", AsyncMock(return_value=False)):
            yield

    @pytest.mark.asyncio
    async def test_remaining_with_usage(self):
        from app.services.quota import get_remaining

        # Mock get_user_plan
        self.mock_fetchrow.side_effect = [
            # get_user_plan query
            {"plan_name": "free", "requests_per_day": 10, "tokens_per_day": 40000,
             "features": "{}", "plan_expires_at": None},
            # usage query
            {"requests_used": 3, "tokens_used": 12000, "cache_hits": 2},
        ]

        result = await get_remaining("user1")
        assert result["requests_remaining"] == 7
        assert result["tokens_remaining"] == 28000
        assert result["plan_name"] == "free"

    @pytest.mark.asyncio
    async def test_remaining_no_usage_yet(self):
        from app.services.quota import get_remaining

        self.mock_fetchrow.side_effect = [
            {"plan_name": "paid", "requests_per_day": 50, "tokens_per_day": 150000,
             "features": "{}", "plan_expires_at": None},
            None,  # no usage row yet
        ]

        result = await get_remaining("user1")
        assert result["requests_remaining"] == 50
        assert result["tokens_remaining"] == 150000


# ╔════════════════════════════════════════════════════════════════╗
# ║  Plan expiry tests                                            ║
# ╚════════════════════════════════════════════════════════════════╝


class TestPlanExpiry:
    @pytest.fixture(autouse=True)
    def _patch(self):
        self.mock_fetchrow = AsyncMock()
        self.mock_fetchval = AsyncMock(return_value="free-plan-id")
        self.mock_execute = AsyncMock()

        with patch("app.services.quota.execute", self.mock_execute), \
             patch("app.services.quota.fetchrow", self.mock_fetchrow), \
             patch("app.services.quota.fetchval", self.mock_fetchval):
            yield

    @pytest.mark.asyncio
    async def test_expired_plan_falls_back_to_free(self):
        from app.services.quota import get_user_plan

        expired_time = datetime.now(timezone.utc) - timedelta(days=1)
        self.mock_fetchrow.return_value = {
            "plan_name": "paid",
            "requests_per_day": 50,
            "tokens_per_day": 150000,
            "features": "{}",
            "plan_expires_at": expired_time,
        }

        plan = await get_user_plan("user1")
        assert plan["plan_name"] == "free"
        assert plan["requests_per_day"] == 10
        assert plan["is_paid"] is False

    @pytest.mark.asyncio
    async def test_active_plan_returns_paid(self):
        from app.services.quota import get_user_plan

        future_time = datetime.now(timezone.utc) + timedelta(days=15)
        self.mock_fetchrow.return_value = {
            "plan_name": "paid",
            "requests_per_day": 50,
            "tokens_per_day": 150000,
            "features": '{"quiz_generation": true}',
            "plan_expires_at": future_time,
        }

        plan = await get_user_plan("user1")
        assert plan["plan_name"] == "paid"
        assert plan["requests_per_day"] == 50
        assert plan["is_paid"] is True
        assert plan["features"]["quiz_generation"] is True

    @pytest.mark.asyncio
    async def test_no_profile_returns_free(self):
        from app.services.quota import get_user_plan

        self.mock_fetchrow.return_value = None

        plan = await get_user_plan("unknown_user")
        assert plan["plan_name"] == "free"


# ╔════════════════════════════════════════════════════════════════╗
# ║  Budget guard tests                                           ║
# ╚════════════════════════════════════════════════════════════════╝


class TestBudgetGuard:
    @pytest.mark.asyncio
    async def test_paid_users_never_affected(self):
        from app.services.quota import should_use_retrieval_only

        with patch("app.services.quota.get_budget_guard_settings", AsyncMock(return_value={
            "is_enabled": True, "threshold_pct": 0.9,
            "manual_retrieval_only": True, "monthly_spend_cap_usd": 0,
        })):
            result = await should_use_retrieval_only(is_paid=True)
            assert result is False

    @pytest.mark.asyncio
    async def test_manual_retrieval_only_affects_free(self):
        from app.services.quota import should_use_retrieval_only

        with patch("app.services.quota.get_budget_guard_settings", AsyncMock(return_value={
            "is_enabled": False, "threshold_pct": 0.9,
            "manual_retrieval_only": True, "monthly_spend_cap_usd": 0,
        })):
            result = await should_use_retrieval_only(is_paid=False)
            assert result is True

    @pytest.mark.asyncio
    async def test_budget_guard_below_threshold_allows(self):
        from app.services.quota import should_use_retrieval_only

        with patch("app.services.quota.get_budget_guard_settings", AsyncMock(return_value={
            "is_enabled": True, "threshold_pct": 0.9,
            "manual_retrieval_only": False, "monthly_spend_cap_usd": 0,
        })), patch("app.services.quota.get_capacity_used_pct", AsyncMock(return_value=0.5)):
            result = await should_use_retrieval_only(is_paid=False)
            assert result is False

    @pytest.mark.asyncio
    async def test_budget_guard_above_threshold_blocks_free(self):
        from app.services.quota import should_use_retrieval_only

        with patch("app.services.quota.get_budget_guard_settings", AsyncMock(return_value={
            "is_enabled": True, "threshold_pct": 0.9,
            "manual_retrieval_only": False, "monthly_spend_cap_usd": 0,
        })), patch("app.services.quota.get_capacity_used_pct", AsyncMock(return_value=0.95)):
            result = await should_use_retrieval_only(is_paid=False)
            assert result is True

    @pytest.mark.asyncio
    async def test_budget_guard_disabled_allows(self):
        from app.services.quota import should_use_retrieval_only

        with patch("app.services.quota.get_budget_guard_settings", AsyncMock(return_value={
            "is_enabled": False, "threshold_pct": 0.9,
            "manual_retrieval_only": False, "monthly_spend_cap_usd": 0,
        })), patch("app.services.quota.get_capacity_used_pct", AsyncMock(return_value=0.99)):
            result = await should_use_retrieval_only(is_paid=False)
            assert result is False


# ╔════════════════════════════════════════════════════════════════╗
# ║  Concurrent quota tests                                       ║
# ╚════════════════════════════════════════════════════════════════╝


class TestConcurrentQuota:
    """
    Verify that concurrent requests cannot exceed the quota limit.

    Uses a simulated atomic counter to model the SQL behavior.
    """

    @pytest.mark.asyncio
    async def test_concurrent_requests_respect_limit(self):
        """
        Simulate 20 concurrent consume_quota calls with a limit of 10.
        At most 10 should succeed.
        """
        counter = {"value": 0}
        lock = asyncio.Lock()

        async def mock_fetchrow_atomic(*args, **kwargs):
            query = args[0] if args else ""
            if "UPDATE" in query and "requests_used" in query:
                async with lock:
                    if counter["value"] < 10:  # limit
                        counter["value"] += 1
                        return {
                            "requests_used": counter["value"],
                            "tokens_used": 0,
                            "cache_hits": 0,
                        }
                    return None  # quota exceeded
            elif "SELECT" in query:
                return {
                    "requests_used": counter["value"],
                    "tokens_used": 0,
                    "cache_hits": 0,
                }
            return None

        with patch("app.services.quota.execute", AsyncMock()), \
             patch("app.services.quota.fetchrow", mock_fetchrow_atomic), \
             patch("app.services.quota.fetchval", AsyncMock()):
            from app.services.quota import consume_quota

            results = await asyncio.gather(
                *[consume_quota("user1", 10, 40000) for _ in range(20)]
            )

            successes = sum(1 for ok, _ in results if ok)
            failures = sum(1 for ok, _ in results if not ok)

            assert successes == 10, f"Expected 10 successes, got {successes}"
            assert failures == 10, f"Expected 10 failures, got {failures}"
