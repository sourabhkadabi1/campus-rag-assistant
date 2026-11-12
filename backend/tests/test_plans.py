"""
Tests for Phase 4 — Plan CRUD and features.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models import (
    PlanCreateRequest,
    PlanGrantRequest,
    PlanResponse,
    PlanUpdateRequest,
)


class TestPlanModels:
    """Test plan Pydantic models."""

    def test_plan_create_valid(self):
        req = PlanCreateRequest(
            name="premium",
            display_name="Premium",
            requests_per_day=100,
            tokens_per_day=500000,
            features={"quiz_generation": True, "longer_answers": True},
        )
        assert req.name == "premium"
        assert req.requests_per_day == 100

    def test_plan_create_min_tokens(self):
        """tokens_per_day must be >= 1000."""
        with pytest.raises(Exception):
            PlanCreateRequest(
                name="bad",
                display_name="Bad",
                requests_per_day=1,
                tokens_per_day=500,
            )

    def test_plan_update_partial(self):
        req = PlanUpdateRequest(requests_per_day=20)
        assert req.requests_per_day == 20
        assert req.display_name is None  # not set

    def test_plan_response_from_attributes(self):
        plan = PlanResponse(
            id="00000000-0000-0000-0000-000000000001",
            name="free",
            display_name="Free",
            requests_per_day=10,
            tokens_per_day=40000,
        )
        assert plan.name == "free"

    def test_plan_grant_request(self):
        req = PlanGrantRequest(
            user_ids=["00000000-0000-0000-0000-000000000001"],
            plan_name="paid",
            duration_days=60,
        )
        assert len(req.user_ids) == 1
        assert req.duration_days == 60

    def test_plan_grant_min_duration(self):
        """Duration must be >= 1."""
        with pytest.raises(Exception):
            PlanGrantRequest(
                user_ids=["00000000-0000-0000-0000-000000000001"],
                plan_name="paid",
                duration_days=0,
            )


# ╔════════════════════════════════════════════════════════════════╗
# ║  Grant plan manually tests (mocked DB)                       ║
# ╚════════════════════════════════════════════════════════════════╝


@pytest.fixture
def grant_mocks():
    """Patch DB helpers for grant tests."""
    mock_fetchrow = AsyncMock()
    mock_execute = AsyncMock()

    with patch("app.services.payment.execute", mock_execute), \
         patch("app.services.payment.fetchrow", mock_fetchrow), \
         patch("app.services.payment.fetchval", AsyncMock()):
        yield {
            "fetchrow": mock_fetchrow,
            "execute": mock_execute,
        }


async def test_grant_success(grant_mocks):
    from app.services.payment import grant_plan_manually

    grant_mocks["fetchrow"].return_value = {"id": "plan-id", "name": "paid"}

    results = await grant_plan_manually(
        user_ids=["user1", "user2"],
        plan_name="paid",
        duration_days=30,
    )
    assert len(results) == 2
    assert results[0]["plan_name"] == "paid"
    assert "expires_at" in results[0]


async def test_grant_unknown_plan_raises(grant_mocks):
    from app.services.payment import grant_plan_manually

    grant_mocks["fetchrow"].return_value = None

    with pytest.raises(ValueError, match="not found"):
        await grant_plan_manually(["user1"], "nonexistent", 30)
