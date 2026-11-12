"""
Quota router — student-facing quota/usage endpoints.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.models import QuotaRemainingResponse, UsageResponse
from app.services.quota import get_remaining, get_user_plan
from app.database import fetch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quota", tags=["quota"])


@router.get("/remaining", response_model=QuotaRemainingResponse)
async def remaining_quota(request: Request) -> QuotaRemainingResponse:
    """
    Return the student's remaining daily quota.

    Requires ``X-User-Id`` header (replaced by auth tokens in production).
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    data = await get_remaining(user_id)
    return QuotaRemainingResponse(**data)


@router.get("/usage", response_model=list[UsageResponse])
async def usage_history(
    request: Request,
    days: int = 7,
):
    """
    Return the student's daily usage for the last *days* days.
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    if days < 1 or days > 90:
        raise HTTPException(400, "days must be between 1 and 90")

    rows = await fetch(
        """SELECT date::text, requests_used, tokens_used, cache_hits
           FROM usage_daily
           WHERE user_id = $1
           ORDER BY date DESC
           LIMIT $2""",
        user_id, days,
    )

    return [
        UsageResponse(
            date=r["date"],
            requests_used=r["requests_used"],
            tokens_used=r["tokens_used"],
            cache_hits=r["cache_hits"],
        )
        for r in rows
    ]
