"""
Quota enforcement service — atomic consume / refund / remaining / budget guard.

Key semantics:
  - Quota check is ATOMIC: a single SQL ``UPDATE … WHERE requests_used < limit RETURNING``
    (or Redis INCR with expiry) guarantees concurrent requests cannot exceed the limit.
  - Cache hits and stored-summary routes do NOT consume quota.
  - If the LLM call fails, the consumed request is refunded.
  - Token usage is updated AFTER the LLM call with real API-reported counts.
  - A student may slightly overshoot on their last question (tokens only).
  - When the global budget guard fires (~90 % combined free-tier capacity),
    FREE users auto-switch to retrieval-only while PAID users keep full answers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import DEFAULT_MODEL_LIMITS, settings
from app.database import execute, fetch, fetchrow, fetchval

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  User plan helpers                                            ║
# ╚════════════════════════════════════════════════════════════════╝


async def get_user_plan(user_id: str) -> dict:
    """
    Return the active plan limits for *user_id*.

    Returns a dict with keys:
      plan_name, requests_per_day, tokens_per_day, features, is_paid
    Falls back to the default (free) plan when:
      - The user has no plan set.
      - The plan has expired.
    """
    row = await fetchrow(
        """SELECT p.name AS plan_name, p.requests_per_day, p.tokens_per_day,
                  p.features, pr.plan_expires_at
           FROM profiles pr
           LEFT JOIN plans p ON pr.plan_id = p.id
           WHERE pr.id = $1""",
        user_id,
    )

    free_defaults = {
        "plan_name": "free",
        "requests_per_day": 10,
        "tokens_per_day": 40_000,
        "features": {},
        "is_paid": False,
    }

    if not row:
        return free_defaults

    # Check plan expiry
    expires = row["plan_expires_at"]
    if expires and expires < datetime.now(timezone.utc):
        # Plan expired — reset to free
        logger.info("Plan expired for user %s — reverting to free", user_id)
        await _reset_to_free(user_id)
        return free_defaults

    plan_name = row["plan_name"] or "free"
    features = row["features"]
    if isinstance(features, str):
        features = json.loads(features)

    return {
        "plan_name": plan_name,
        "requests_per_day": row["requests_per_day"] or 10,
        "tokens_per_day": row["tokens_per_day"] or 40_000,
        "features": features or {},
        "is_paid": plan_name != "free",
    }


async def _reset_to_free(user_id: str) -> None:
    """Reset a user's plan to the default free plan."""
    free_plan_id = await fetchval(
        "SELECT id FROM plans WHERE is_default = TRUE LIMIT 1"
    )
    if free_plan_id:
        await execute(
            """UPDATE profiles
               SET plan_id = $1, plan_expires_at = NULL, updated_at = NOW()
               WHERE id = $2""",
            free_plan_id, user_id,
        )


# ╔════════════════════════════════════════════════════════════════╗
# ║  Atomic quota consume / refund / remaining                    ║
# ╚════════════════════════════════════════════════════════════════╝


async def consume_quota(
    user_id: str,
    requests_limit: int,
    tokens_limit: int,
) -> tuple[bool, dict]:
    """
    Atomically consume 1 request from the user's daily quota.

    Returns ``(ok, usage_dict)`` where *ok* is False when the user has
    exceeded either the request or token limit.

    The token check allows slight overshoot on the last question — tokens are
    only updated after the LLM call via :func:`record_tokens`.  Here we only
    block if the user is ALREADY at or beyond the token limit.
    """
    # Ensure a row exists for today
    await execute(
        """INSERT INTO usage_daily (user_id, date, requests_used, tokens_used, cache_hits)
           VALUES ($1, CURRENT_DATE, 0, 0, 0)
           ON CONFLICT (user_id, date) DO NOTHING""",
        user_id,
    )

    # Atomic increment with guard — single statement, race-safe
    row = await fetchrow(
        """UPDATE usage_daily
           SET requests_used = requests_used + 1
           WHERE user_id = $1 AND date = CURRENT_DATE
             AND requests_used < $2
           RETURNING requests_used, tokens_used, cache_hits""",
        user_id, requests_limit,
    )

    if not row:
        # Quota exceeded (requests)
        usage = await fetchrow(
            """SELECT requests_used, tokens_used, cache_hits
               FROM usage_daily WHERE user_id = $1 AND date = CURRENT_DATE""",
            user_id,
        )
        return False, {
            "requests_used": usage["requests_used"] if usage else requests_limit,
            "tokens_used": usage["tokens_used"] if usage else 0,
            "cache_hits": usage["cache_hits"] if usage else 0,
            "reason": "requests_exceeded",
        }

    # Check token limit (block if already at limit; allow overshoot on last Q)
    if row["tokens_used"] >= tokens_limit:
        # Refund the request we just consumed
        await refund_quota(user_id, requests=1)
        return False, {
            "requests_used": row["requests_used"] - 1,
            "tokens_used": row["tokens_used"],
            "cache_hits": row["cache_hits"],
            "reason": "tokens_exceeded",
        }

    return True, {
        "requests_used": row["requests_used"],
        "tokens_used": row["tokens_used"],
        "cache_hits": row["cache_hits"],
    }


async def refund_quota(user_id: str, requests: int = 1, tokens: int = 0) -> None:
    """
    Refund quota after an LLM call failure.

    Decrements the counters but clamps at 0 to avoid negatives.
    """
    await execute(
        """UPDATE usage_daily
           SET requests_used = GREATEST(0, requests_used - $2),
               tokens_used   = GREATEST(0, tokens_used - $3)
           WHERE user_id = $1 AND date = CURRENT_DATE""",
        user_id, requests, tokens,
    )
    logger.debug("Refunded quota for %s: -%d requests, -%d tokens", user_id, requests, tokens)


async def record_tokens(user_id: str, tokens: int) -> None:
    """
    Record real API-reported token usage after a successful LLM call.

    Called with the ``input_tokens + output_tokens`` from the API response.
    """
    if tokens <= 0:
        return
    await execute(
        """UPDATE usage_daily
           SET tokens_used = tokens_used + $2
           WHERE user_id = $1 AND date = CURRENT_DATE""",
        user_id, tokens,
    )


async def record_cache_hit(user_id: str) -> None:
    """Increment the cache-hits counter (no quota consumed)."""
    await execute(
        """INSERT INTO usage_daily (user_id, date, requests_used, tokens_used, cache_hits)
           VALUES ($1, CURRENT_DATE, 0, 0, 1)
           ON CONFLICT (user_id, date) DO UPDATE
           SET cache_hits = usage_daily.cache_hits + 1""",
        user_id,
    )


async def get_remaining(user_id: str) -> dict:
    """
    Return the remaining quota for the current day.

    Dict keys: requests_remaining, tokens_remaining, requests_limit,
    tokens_limit, requests_used, tokens_used, cache_hits_today,
    plan_name, is_retrieval_only, resets_at.
    """
    plan = await get_user_plan(user_id)
    usage = await fetchrow(
        """SELECT requests_used, tokens_used, cache_hits
           FROM usage_daily WHERE user_id = $1 AND date = CURRENT_DATE""",
        user_id,
    )

    requests_used = usage["requests_used"] if usage else 0
    tokens_used = usage["tokens_used"] if usage else 0
    cache_hits = usage["cache_hits"] if usage else 0

    req_limit = plan["requests_per_day"]
    tok_limit = plan["tokens_per_day"]

    # Budget guard check
    retrieval_only = await should_use_retrieval_only(plan["is_paid"])

    # Midnight UTC reset
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        "requests_remaining": max(0, req_limit - requests_used),
        "tokens_remaining": max(0, tok_limit - tokens_used),
        "requests_limit": req_limit,
        "tokens_limit": tok_limit,
        "requests_used": requests_used,
        "tokens_used": tokens_used,
        "cache_hits_today": cache_hits,
        "plan_name": plan["plan_name"],
        "is_retrieval_only": retrieval_only,
        "resets_at": tomorrow.isoformat(),
    }


# ╔════════════════════════════════════════════════════════════════╗
# ║  Global budget guard                                          ║
# ╚════════════════════════════════════════════════════════════════╝


async def get_budget_guard_settings() -> dict:
    """Load budget guard settings from DB (single-row table)."""
    row = await fetchrow(
        """SELECT is_enabled, threshold_pct, manual_retrieval_only, monthly_spend_cap_usd
           FROM budget_guard_settings LIMIT 1"""
    )
    if not row:
        return {
            "is_enabled": False,
            "threshold_pct": 0.90,
            "manual_retrieval_only": False,
            "monthly_spend_cap_usd": 0.0,
        }
    return {
        "is_enabled": row["is_enabled"],
        "threshold_pct": float(row["threshold_pct"]),
        "manual_retrieval_only": row["manual_retrieval_only"],
        "monthly_spend_cap_usd": float(row["monthly_spend_cap_usd"]),
    }


async def get_capacity_used_pct() -> float:
    """
    Calculate what percentage of combined free-provider daily capacity is used.

    Uses the rate counter data for today across all MODEL_CHAIN models.
    """
    from app.services.rate_counter import get_current_date_str, get_rate_store

    store = get_rate_store()
    date_str = get_current_date_str()

    total_rpd_limit = 0
    total_rpd_used = 0

    for model_id in settings.model_chain_list:
        limits = DEFAULT_MODEL_LIMITS.get(model_id, {})
        rpd_limit = limits.get("rpd", 100)
        total_rpd_limit += rpd_limit
        rpd_used = await store.get_rpd(model_id, date_str)
        total_rpd_used += rpd_used

    if total_rpd_limit == 0:
        return 0.0

    return total_rpd_used / total_rpd_limit


async def should_use_retrieval_only(is_paid: bool) -> bool:
    """
    Check whether the current request should be retrieval-only.

    Returns True when:
      - Admin has manually toggled "exam-week mode" (manual_retrieval_only), OR
      - Budget guard is enabled AND capacity exceeds threshold AND user is FREE.
    Paid users are never affected by the automatic budget guard.
    """
    if is_paid:
        return False

    try:
        guard = await get_budget_guard_settings()
    except Exception:
        return False

    # Admin manual override (exam-week mode)
    if guard["manual_retrieval_only"]:
        return True

    if not guard["is_enabled"]:
        return False

    capacity = await get_capacity_used_pct()
    threshold = guard["threshold_pct"]

    if capacity >= threshold:
        logger.info(
            "Budget guard triggered: %.1f%% capacity used (threshold %.0f%%) — "
            "FREE users → retrieval-only",
            capacity * 100, threshold * 100,
        )
        return True

    return False


async def update_budget_guard(
    is_enabled: Optional[bool] = None,
    manual_retrieval_only: Optional[bool] = None,
    threshold_pct: Optional[float] = None,
    monthly_spend_cap_usd: Optional[float] = None,
    updated_by: Optional[str] = None,
) -> dict:
    """Update budget guard settings (admin only)."""
    guard = await get_budget_guard_settings()

    new_enabled = is_enabled if is_enabled is not None else guard["is_enabled"]
    new_manual = manual_retrieval_only if manual_retrieval_only is not None else guard["manual_retrieval_only"]
    new_threshold = threshold_pct if threshold_pct is not None else guard["threshold_pct"]
    new_cap = monthly_spend_cap_usd if monthly_spend_cap_usd is not None else guard["monthly_spend_cap_usd"]

    await execute(
        """UPDATE budget_guard_settings
           SET is_enabled = $1, manual_retrieval_only = $2,
               threshold_pct = $3, monthly_spend_cap_usd = $4,
               updated_at = NOW(), updated_by = $5""",
        new_enabled, new_manual, new_threshold, new_cap, updated_by,
    )

    return {
        "is_enabled": new_enabled,
        "manual_retrieval_only": new_manual,
        "threshold_pct": new_threshold,
        "monthly_spend_cap_usd": new_cap,
    }


async def get_budget_guard_status() -> dict:
    """Full budget guard status including capacity calculation."""
    guard = await get_budget_guard_settings()
    capacity = await get_capacity_used_pct()

    return {
        "is_active": guard["is_enabled"] and capacity >= guard["threshold_pct"],
        "manual_retrieval_only": guard["manual_retrieval_only"],
        "capacity_used_pct": round(capacity, 4),
        "threshold_pct": guard["threshold_pct"],
        "free_users_affected": (
            guard["manual_retrieval_only"]
            or (guard["is_enabled"] and capacity >= guard["threshold_pct"])
        ),
        "monthly_spend_usd": 0.0,  # TODO: aggregate from monthly_spend table
        "monthly_cap_usd": guard["monthly_spend_cap_usd"],
    }
