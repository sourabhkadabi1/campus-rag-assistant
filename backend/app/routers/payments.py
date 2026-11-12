"""
Payments router — Razorpay checkout + webhook.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.models import (
    PaymentOrderRequest,
    PaymentOrderResponse,
    PaymentWebhookPayload,
)
from app.services.payment import create_order, process_payment

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-order", response_model=PaymentOrderResponse)
async def create_payment_order(request: Request, body: PaymentOrderRequest):
    """
    Create a Razorpay order for the student to complete checkout.

    Requires ``X-User-Id`` header (replaced by auth tokens in production).
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    try:
        result = await create_order(user_id, body.plan_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return PaymentOrderResponse(**result)


@router.post("/webhook")
async def payment_webhook(body: PaymentWebhookPayload):
    """
    Razorpay payment webhook — called by Razorpay after successful payment.

    The signature is verified (HMAC-SHA256) before any state change.
    This endpoint is idempotent: re-processing a webhook is safe.
    """
    try:
        result = await process_payment(
            razorpay_order_id=body.razorpay_order_id,
            razorpay_payment_id=body.razorpay_payment_id,
            razorpay_signature=body.razorpay_signature,
        )
    except ValueError as exc:
        logger.warning("Webhook rejected: %s", exc)
        raise HTTPException(400, str(exc))

    return result


@router.post("/verify")
async def verify_payment(body: PaymentWebhookPayload):
    """
    Client-side payment verification — called by the frontend after
    Razorpay checkout completes.

    Performs the same verification as the webhook.
    """
    try:
        result = await process_payment(
            razorpay_order_id=body.razorpay_order_id,
            razorpay_payment_id=body.razorpay_payment_id,
            razorpay_signature=body.razorpay_signature,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return result
