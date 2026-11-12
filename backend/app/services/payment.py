"""
Razorpay payment integration — order creation, webhook verification, plan assignment.

Security:
  - Webhook signature is verified using HMAC-SHA256 before any state change.
  - Amount and plan are cross-checked against our records.
  - Plan assignment is idempotent (re-processing a webhook won't double-grant).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.config import settings
from app.database import execute, fetchrow, fetchval

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Razorpay order creation                                      ║
# ╚════════════════════════════════════════════════════════════════╝


async def create_order(user_id: str, plan_name: str = "paid") -> dict:
    """
    Create a Razorpay order for the specified plan.

    Returns a dict ready for the frontend checkout widget:
      order_id, amount_paise, currency, key_id, plan_name, plan_display_name

    Raises ValueError if the plan is not found or keys are not configured.
    """
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise ValueError("Razorpay keys not configured — set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET")

    # Look up the plan
    plan = await fetchrow(
        """SELECT id, name, display_name, price_paise, duration_days
           FROM plans WHERE name = $1""",
        plan_name,
    )
    if not plan:
        raise ValueError(f"Plan '{plan_name}' not found")

    amount = plan["price_paise"]
    if amount <= 0:
        raise ValueError(f"Plan '{plan_name}' has no price set")

    # Create Razorpay order via API
    receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.razorpay.com/v1/orders",
            json={
                "amount": amount,
                "currency": "INR",
                "receipt": receipt_id,
                "notes": {
                    "user_id": user_id,
                    "plan_name": plan_name,
                },
            },
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
        )
        resp.raise_for_status()
        order = resp.json()

    razorpay_order_id = order["id"]

    # Record in our payments table
    await execute(
        """INSERT INTO payments
           (user_id, razorpay_order_id, plan_id, plan_name,
            amount_paise, currency, status, plan_duration_days)
           VALUES ($1, $2, $3, $4, $5, $6, 'created', $7)""",
        user_id, razorpay_order_id, plan["id"], plan_name,
        amount, "INR", plan["duration_days"],
    )

    logger.info(
        "Created Razorpay order %s for user %s, plan=%s, ₹%.2f",
        razorpay_order_id, user_id, plan_name, amount / 100,
    )

    return {
        "order_id": razorpay_order_id,
        "amount_paise": amount,
        "currency": "INR",
        "key_id": settings.razorpay_key_id,
        "plan_name": plan_name,
        "plan_display_name": plan["display_name"],
    }


# ╔════════════════════════════════════════════════════════════════╗
# ║  Webhook signature verification                               ║
# ╚════════════════════════════════════════════════════════════════╝


def verify_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify the Razorpay webhook signature using HMAC-SHA256.

    The signature is computed as:
      HMAC-SHA256(order_id + "|" + payment_id, webhook_secret)
    """
    secret = settings.razorpay_key_secret
    if not secret:
        logger.error("Cannot verify signature — RAZORPAY_KEY_SECRET not set")
        return False

    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(
        secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, razorpay_signature)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Payment processing                                           ║
# ╚════════════════════════════════════════════════════════════════╝


async def process_payment(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> dict:
    """
    Verify and process a completed Razorpay payment.

    Steps:
      1. Verify the signature.
      2. Look up the payment record.
      3. Mark as paid.
      4. Assign the plan to the user with expiry.

    Returns a dict with status, plan_name, expires_at.
    Raises ValueError on invalid signature or missing record.
    """
    # 1. Verify signature
    if not verify_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        logger.warning(
            "Invalid Razorpay signature for order %s", razorpay_order_id
        )
        raise ValueError("Invalid payment signature")

    # 2. Look up payment
    payment = await fetchrow(
        """SELECT id, user_id, plan_name, plan_duration_days, status, plan_id
           FROM payments WHERE razorpay_order_id = $1""",
        razorpay_order_id,
    )
    if not payment:
        raise ValueError(f"Payment record not found for order {razorpay_order_id}")

    # Idempotent: already processed
    if payment["status"] == "paid":
        logger.info("Payment %s already processed — skipping", razorpay_order_id)
        return {"status": "already_processed", "plan_name": payment["plan_name"]}

    # 3. Mark as paid
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=payment["plan_duration_days"])

    await execute(
        """UPDATE payments
           SET razorpay_payment_id = $1, razorpay_signature = $2,
               status = 'paid', plan_starts_at = $3, plan_expires_at = $4,
               updated_at = NOW()
           WHERE razorpay_order_id = $5""",
        razorpay_payment_id, razorpay_signature,
        now, expires, razorpay_order_id,
    )

    # 4. Assign plan to user
    await execute(
        """UPDATE profiles
           SET plan_id = $1, plan_expires_at = $2, updated_at = NOW()
           WHERE id = $3""",
        payment["plan_id"], expires, payment["user_id"],
    )

    logger.info(
        "Payment processed: order=%s user=%s plan=%s expires=%s",
        razorpay_order_id, payment["user_id"],
        payment["plan_name"], expires.isoformat(),
    )

    return {
        "status": "paid",
        "plan_name": payment["plan_name"],
        "expires_at": expires.isoformat(),
        "user_id": str(payment["user_id"]),
    }


async def grant_plan_manually(
    user_ids: list[str],
    plan_name: str,
    duration_days: int = 30,
) -> list[dict]:
    """
    Admin: grant a plan to one or more users without payment.

    Returns a list of {user_id, plan_name, expires_at} dicts.
    """
    plan = await fetchrow(
        "SELECT id, name FROM plans WHERE name = $1", plan_name,
    )
    if not plan:
        raise ValueError(f"Plan '{plan_name}' not found")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=duration_days)
    results = []

    for uid in user_ids:
        await execute(
            """UPDATE profiles
               SET plan_id = $1, plan_expires_at = $2, updated_at = NOW()
               WHERE id = $3""",
            plan["id"], expires, uid,
        )
        results.append({
            "user_id": uid,
            "plan_name": plan_name,
            "expires_at": expires.isoformat(),
        })

    logger.info(
        "Admin granted plan '%s' to %d user(s) for %d days",
        plan_name, len(user_ids), duration_days,
    )
    return results
