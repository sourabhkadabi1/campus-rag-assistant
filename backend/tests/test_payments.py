"""
Tests for Phase 4 — Razorpay payment signature verification and processing.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ╔════════════════════════════════════════════════════════════════╗
# ║  Signature verification tests (no DB needed)                  ║
# ╚════════════════════════════════════════════════════════════════╝


class TestSignatureVerification:
    """Test Razorpay HMAC-SHA256 signature verification."""

    def _make_signature(self, order_id: str, payment_id: str, secret: str) -> str:
        message = f"{order_id}|{payment_id}"
        return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    def test_valid_signature(self):
        from app.services.payment import verify_signature

        secret = "test_secret_123"
        order_id = "order_abc"
        payment_id = "pay_xyz"
        sig = self._make_signature(order_id, payment_id, secret)

        with patch("app.services.payment.settings") as mock_settings:
            mock_settings.razorpay_key_secret = secret
            assert verify_signature(order_id, payment_id, sig) is True

    def test_invalid_signature(self):
        from app.services.payment import verify_signature

        with patch("app.services.payment.settings") as mock_settings:
            mock_settings.razorpay_key_secret = "test_secret_123"
            assert verify_signature("order_abc", "pay_xyz", "wrong_sig") is False

    def test_empty_secret_rejects(self):
        from app.services.payment import verify_signature

        with patch("app.services.payment.settings") as mock_settings:
            mock_settings.razorpay_key_secret = ""
            assert verify_signature("order_abc", "pay_xyz", "any") is False


# ╔════════════════════════════════════════════════════════════════╗
# ║  Payment processing tests (mocked DB)                        ║
# ╚════════════════════════════════════════════════════════════════╝


class TestProcessPayment:
    """Test payment processing with mocked database."""

    @pytest.fixture(autouse=True)
    def _patch(self):
        self.mock_execute = AsyncMock()
        self.mock_fetchrow = AsyncMock()
        self.mock_fetchval = AsyncMock()

        with patch("app.services.payment.execute", self.mock_execute), \
             patch("app.services.payment.fetchrow", self.mock_fetchrow), \
             patch("app.services.payment.fetchval", self.mock_fetchval):
            yield

    @pytest.mark.asyncio
    async def test_process_valid_payment(self):
        from app.services.payment import process_payment

        secret = "test_secret"
        order_id = "order_123"
        payment_id = "pay_456"
        sig = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        self.mock_fetchrow.return_value = {
            "id": "pay-record-id",
            "user_id": "user-uuid",
            "plan_name": "paid",
            "plan_duration_days": 30,
            "status": "created",
            "plan_id": "plan-uuid",
        }

        with patch("app.services.payment.settings") as mock_settings:
            mock_settings.razorpay_key_secret = secret
            result = await process_payment(order_id, payment_id, sig)

        assert result["status"] == "paid"
        assert result["plan_name"] == "paid"
        assert "expires_at" in result

    @pytest.mark.asyncio
    async def test_process_invalid_signature_raises(self):
        from app.services.payment import process_payment

        with patch("app.services.payment.settings") as mock_settings:
            mock_settings.razorpay_key_secret = "test_secret"
            with pytest.raises(ValueError, match="Invalid payment signature"):
                await process_payment("order_123", "pay_456", "bad_sig")

    @pytest.mark.asyncio
    async def test_process_already_paid_is_idempotent(self):
        from app.services.payment import process_payment

        secret = "test_secret"
        order_id = "order_123"
        payment_id = "pay_456"
        sig = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        self.mock_fetchrow.return_value = {
            "id": "pay-record-id",
            "user_id": "user-uuid",
            "plan_name": "paid",
            "plan_duration_days": 30,
            "status": "paid",  # already processed
            "plan_id": "plan-uuid",
        }

        with patch("app.services.payment.settings") as mock_settings:
            mock_settings.razorpay_key_secret = secret
            result = await process_payment(order_id, payment_id, sig)

        assert result["status"] == "already_processed"

    @pytest.mark.asyncio
    async def test_process_missing_order_raises(self):
        from app.services.payment import process_payment

        secret = "test_secret"
        order_id = "order_unknown"
        payment_id = "pay_456"
        sig = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        self.mock_fetchrow.return_value = None

        with patch("app.services.payment.settings") as mock_settings:
            mock_settings.razorpay_key_secret = secret
            with pytest.raises(ValueError, match="not found"):
                await process_payment(order_id, payment_id, sig)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Pydantic model tests                                        ║
# ╚════════════════════════════════════════════════════════════════╝


class TestPaymentModels:
    def test_payment_order_request_defaults(self):
        from app.models import PaymentOrderRequest
        req = PaymentOrderRequest()
        assert req.plan_name == "paid"

    def test_payment_webhook_payload(self):
        from app.models import PaymentWebhookPayload
        p = PaymentWebhookPayload(
            razorpay_order_id="order_123",
            razorpay_payment_id="pay_456",
            razorpay_signature="sig_abc",
        )
        assert p.razorpay_order_id == "order_123"

    def test_quota_remaining_response(self):
        from app.models import QuotaRemainingResponse
        q = QuotaRemainingResponse(
            requests_remaining=7,
            tokens_remaining=28000,
            requests_limit=10,
            tokens_limit=40000,
            requests_used=3,
            tokens_used=12000,
        )
        assert q.requests_remaining == 7
        assert q.plan_name == "free"

    def test_budget_guard_status(self):
        from app.models import BudgetGuardStatus
        bg = BudgetGuardStatus(
            is_active=True,
            capacity_used_pct=0.92,
            threshold_pct=0.90,
            free_users_affected=True,
        )
        assert bg.is_active is True
