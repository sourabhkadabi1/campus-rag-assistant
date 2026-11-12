"""
Plans router — admin CRUD for subscription plans + student read.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.database import execute, fetch, fetchrow, fetchval
from app.models import (
    PlanCreateRequest,
    PlanGrantRequest,
    PlanResponse,
    PlanUpdateRequest,
)
from app.services.payment import grant_plan_manually

logger = logging.getLogger(__name__)
router = APIRouter(tags=["plans"])


# ── Student: list plans ──────────────────────────────────────────


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans():
    """List all available subscription plans (public)."""
    rows = await fetch(
        """SELECT id, name, display_name, requests_per_day, tokens_per_day,
                  features, is_default, created_at
           FROM plans ORDER BY requests_per_day ASC"""
    )
    results = []
    for r in rows:
        features = r["features"]
        if isinstance(features, str):
            features = json.loads(features)
        results.append(
            PlanResponse(
                id=r["id"],
                name=r["name"],
                display_name=r["display_name"],
                requests_per_day=r["requests_per_day"],
                tokens_per_day=r["tokens_per_day"],
                features=features or {},
                is_default=r["is_default"],
                created_at=r["created_at"],
            )
        )
    return results


# ── Admin: create plan ───────────────────────────────────────────


@router.post("/admin/plans", response_model=PlanResponse, status_code=201)
async def create_plan(body: PlanCreateRequest):
    """Create a new subscription plan (admin only)."""
    existing = await fetchval(
        "SELECT 1 FROM plans WHERE name = $1", body.name
    )
    if existing:
        raise HTTPException(409, f"Plan '{body.name}' already exists")

    features_json = json.dumps(body.features)

    row = await fetchrow(
        """INSERT INTO plans (name, display_name, requests_per_day,
                              tokens_per_day, features, is_default)
           VALUES ($1, $2, $3, $4, $5::jsonb, $6)
           RETURNING id, name, display_name, requests_per_day,
                     tokens_per_day, features, is_default, created_at""",
        body.name, body.display_name, body.requests_per_day,
        body.tokens_per_day, features_json, body.is_default,
    )

    features = row["features"]
    if isinstance(features, str):
        features = json.loads(features)

    logger.info("Created plan: %s", body.name)
    return PlanResponse(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"],
        requests_per_day=row["requests_per_day"],
        tokens_per_day=row["tokens_per_day"],
        features=features or {},
        is_default=row["is_default"],
        created_at=row["created_at"],
    )


# ── Admin: update plan ───────────────────────────────────────────


@router.put("/admin/plans/{plan_name}", response_model=PlanResponse)
async def update_plan(plan_name: str, body: PlanUpdateRequest):
    """Update an existing subscription plan (admin only)."""
    existing = await fetchrow(
        """SELECT id, name, display_name, requests_per_day, tokens_per_day,
                  features, is_default, created_at
           FROM plans WHERE name = $1""",
        plan_name,
    )
    if not existing:
        raise HTTPException(404, f"Plan '{plan_name}' not found")

    new_display = body.display_name or existing["display_name"]
    new_rpd = body.requests_per_day if body.requests_per_day is not None else existing["requests_per_day"]
    new_tpd = body.tokens_per_day if body.tokens_per_day is not None else existing["tokens_per_day"]

    new_features = existing["features"]
    if body.features is not None:
        new_features = json.dumps(body.features)
    elif isinstance(new_features, dict):
        new_features = json.dumps(new_features)

    new_default = body.is_default if body.is_default is not None else existing["is_default"]

    row = await fetchrow(
        """UPDATE plans
           SET display_name = $1, requests_per_day = $2, tokens_per_day = $3,
               features = $4::jsonb, is_default = $5, updated_at = NOW()
           WHERE name = $6
           RETURNING id, name, display_name, requests_per_day,
                     tokens_per_day, features, is_default, created_at""",
        new_display, new_rpd, new_tpd, new_features, new_default, plan_name,
    )

    features = row["features"]
    if isinstance(features, str):
        features = json.loads(features)

    logger.info("Updated plan: %s", plan_name)
    return PlanResponse(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"],
        requests_per_day=row["requests_per_day"],
        tokens_per_day=row["tokens_per_day"],
        features=features or {},
        is_default=row["is_default"],
        created_at=row["created_at"],
    )


# ── Admin: delete plan ───────────────────────────────────────────


@router.delete("/admin/plans/{plan_name}")
async def delete_plan(plan_name: str):
    """Delete a plan (admin only). Cannot delete the default plan."""
    existing = await fetchrow(
        "SELECT id, is_default FROM plans WHERE name = $1", plan_name
    )
    if not existing:
        raise HTTPException(404, f"Plan '{plan_name}' not found")
    if existing["is_default"]:
        raise HTTPException(400, "Cannot delete the default plan")

    # Move affected users to the default plan
    default_id = await fetchval(
        "SELECT id FROM plans WHERE is_default = TRUE LIMIT 1"
    )
    if default_id:
        await execute(
            """UPDATE profiles
               SET plan_id = $1, plan_expires_at = NULL, updated_at = NOW()
               WHERE plan_id = $2""",
            default_id, existing["id"],
        )

    await execute("DELETE FROM plans WHERE name = $1", plan_name)
    logger.info("Deleted plan: %s", plan_name)
    return {"name": plan_name, "deleted": True}


# ── Admin: grant plan manually ───────────────────────────────────


@router.post("/admin/plans/grant")
async def grant_plan(body: PlanGrantRequest):
    """
    Manually grant a plan to one or more users (admin only).

    Useful when the college pays for a batch of students, or for
    granting complimentary access.
    """
    user_ids = [str(uid) for uid in body.user_ids]
    results = await grant_plan_manually(user_ids, body.plan_name, body.duration_days)
    return {"granted": len(results), "details": results}
