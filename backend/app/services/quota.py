"""
Quota enforcement service — atomic consume / refund / remaining / budget guard.

Key semantics:
  - Quota check is ATOMIC: a single SQL ``UPDATE … WHERE units_used < limit RETURNING``
    guarantees concurrent requests cannot exceed the limit.
  - Cache hits and stored-summary routes do NOT consume quota.
  - If the LLM call fails, the consumed units are refunded.
  - Token usage is updated AFTER the LLM call with real API-reported counts.
  - A student may slightly overshoot on their last question (tokens only).
  - When the global budget guard fires (~90 % combined free-tier capacity),
    FREE users auto-switch to retrieval-only while PAID users keep full answers.
  - Balance guard: if account balance < PAID_MIN_BALANCE_USD, paid users
    also get retrieval-only answers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import DEFAULT_MODEL_LIMITS, DEFAULT_MODEL_PRICES, settings
from app.database import execute, fetch, fetchrow, fetchval

logger = logging.getLogger(__name__)


def _row_val(row, key: str, default=None):
    """Safely extract a key from a DB Record or dict mock."""
    if not row:
        return default
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default


# ╔════════════════════════════════════════════════════════════════╗
# ║  User plan helpers                                            ║
# ╚════════════════════════════════════════════════════════════════╝


async def get_user_plan(user_id: str) -> dict:
    """
    Return the active plan limits for *user_id*.

    Returns a dict with keys:
      plan_name, requests_per_day, tokens_per_day, features, is_paid,
      thinking_credits_per_day
    Falls back to the default (free) plan when:
      - The user has no plan set.
      - The plan has expired.
    """
    row = await fetchrow(
        """SELECT p.name AS plan_name, p.requests_per_day, p.tokens_per_day,
                  p.features, pr.plan_expires_at,
                  COALESCE(p.thinking_credits_per_day, 0) AS thinking_credits_per_day
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
        "thinking_credits_per_day": 0,
    }

    if not row:
        return free_defaults

    # Check plan expiry
    expires = _row_val(row, "plan_expires_at")
    if expires and expires < datetime.now(timezone.utc):
        logger.info("Plan expired for user %s — reverting to free", user_id)
        await _reset_to_free(user_id)
        return free_defaults

    plan_name = _row_val(row, "plan_name") or "free"
    features = _row_val(row, "features")
    if isinstance(features, str):
        features = json.loads(features)

    return {
        "plan_name": plan_name,
        "requests_per_day": _row_val(row, "requests_per_day", 10) or 10,
        "tokens_per_day": _row_val(row, "tokens_per_day", 40_000) or 40_000,
        "features": features or {},
        "is_paid": plan_name != "free",
        "thinking_credits_per_day": _row_val(row, "thinking_credits_per_day", 0),
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
    units: int = 1,
) -> tuple[bool, dict]:
    """
    Atomically consume *units* from the user's daily quota.

    Returns ``(ok, usage_dict)`` where *ok* is False when the user has
    exceeded either the unit or token limit.

    The token check allows slight overshoot on the last question — tokens are
    only updated after the LLM call via :func:`record_tokens`.  Here we only
    block if the user is ALREADY at or beyond the token limit.
    """
    # Ensure a row exists for today
    await execute(
        """INSERT INTO usage_daily (user_id, date, requests_used, tokens_used, cache_hits, units_used, thinking_credits_used)
           VALUES ($1, CURRENT_DATE, 0, 0, 0, 0, 0)
           ON CONFLICT (user_id, date) DO NOTHING""",
        user_id,
    )

    # Atomic increment with guard — single statement, race-safe
    # Check against units_used (the new currency) but also increment requests_used for backward compat
    row = await fetchrow(
        """UPDATE usage_daily
           SET requests_used = requests_used + 1,
               units_used = units_used + $3
           WHERE user_id = $1 AND date = CURRENT_DATE
             AND units_used + $3 <= $2
           RETURNING requests_used, tokens_used, cache_hits, units_used""",
        user_id, requests_limit, units,
    )

    if not row:
        # Quota exceeded (units)
        usage = await fetchrow(
            """SELECT requests_used, tokens_used, cache_hits, units_used
               FROM usage_daily WHERE user_id = $1 AND date = CURRENT_DATE""",
            user_id,
        )
        req_used = _row_val(usage, "requests_used", requests_limit)
        return False, {
            "requests_used": req_used,
            "tokens_used": _row_val(usage, "tokens_used", 0),
            "cache_hits": _row_val(usage, "cache_hits", 0),
            "units_used": _row_val(usage, "units_used", req_used),
            "reason": "requests_exceeded",
        }

    tok_used = _row_val(row, "tokens_used", 0)
    req_used = _row_val(row, "requests_used", 1)
    un_used = _row_val(row, "units_used", req_used)
    c_hits = _row_val(row, "cache_hits", 0)

    # Check token limit (block if already at limit; allow overshoot on last Q)
    if tok_used >= tokens_limit:
        # Refund the units we just consumed
        await refund_quota(user_id, units=units)
        return False, {
            "requests_used": req_used - 1,
            "tokens_used": tok_used,
            "cache_hits": c_hits,
            "units_used": max(0, un_used - units),
            "reason": "tokens_exceeded",
        }

    return True, {
        "requests_used": req_used,
        "tokens_used": tok_used,
        "cache_hits": c_hits,
        "units_used": un_used,
    }


async def refund_quota(
    user_id: str,
    requests: int = 1,
    tokens: int = 0,
    units: int | None = None,
) -> None:
    """
    Refund quota after an LLM call failure.

    Decrements the counters but clamps at 0 to avoid negatives.
    Supports both requests=... and units=... parameter names.
    """
    actual_units = units if units is not None else requests
    await execute(
        """UPDATE usage_daily
           SET requests_used = GREATEST(0, requests_used - $2),
               units_used    = GREATEST(0, units_used - $3),
               tokens_used   = GREATEST(0, tokens_used - $4)
           WHERE user_id = $1 AND date = CURRENT_DATE""",
        user_id, requests, actual_units, tokens,
    )
    logger.debug("Refunded quota for %s: -%d requests, -%d units, -%d tokens", user_id, requests, actual_units, tokens)


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
        """INSERT INTO usage_daily (user_id, date, requests_used, tokens_used, cache_hits, units_used, thinking_credits_used)
           VALUES ($1, CURRENT_DATE, 0, 0, 1, 0, 0)
           ON CONFLICT (user_id, date) DO UPDATE
           SET cache_hits = usage_daily.cache_hits + 1""",
        user_id,
    )


# ╔════════════════════════════════════════════════════════════════╗
# ║  Thinking credits                                             ║
# ╚════════════════════════════════════════════════════════════════╝


async def consume_thinking_credit(user_id: str, daily_limit: int) -> tuple[bool, int]:
    """
    Atomically consume one thinking credit for today.

    Returns ``(ok, credits_used_after)``; ok=False when limit reached.
    """
    # Ensure row exists
    await execute(
        """INSERT INTO usage_daily (user_id, date, requests_used, tokens_used, cache_hits, units_used, thinking_credits_used)
           VALUES ($1, CURRENT_DATE, 0, 0, 0, 0, 0)
           ON CONFLICT (user_id, date) DO NOTHING""",
        user_id,
    )

    row = await fetchrow(
        """UPDATE usage_daily
           SET thinking_credits_used = thinking_credits_used + 1
           WHERE user_id = $1 AND date = CURRENT_DATE
             AND thinking_credits_used < $2
           RETURNING thinking_credits_used""",
        user_id, daily_limit,
    )
    if not row:
        return False, daily_limit
    return True, row["thinking_credits_used"]


async def refund_thinking_credit(user_id: str) -> None:
    """Refund one thinking credit on failure."""
    await execute(
        """UPDATE usage_daily
           SET thinking_credits_used = GREATEST(0, thinking_credits_used - 1)
           WHERE user_id = $1 AND date = CURRENT_DATE""",
        user_id,
    )


async def get_thinking_left_today(user_id: str, daily_limit: int) -> int:
    """Return the number of thinking credits remaining today."""
    row = await fetchrow(
        """SELECT thinking_credits_used FROM usage_daily
           WHERE user_id = $1 AND date = CURRENT_DATE""",
        user_id,
    )
    used = row["thinking_credits_used"] if row else 0
    return max(0, daily_limit - used)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Cost tracking                                                ║
# ╚════════════════════════════════════════════════════════════════╝


def compute_cost_usd(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int = 0,
) -> float:
    """
    Compute the cost in USD for a request based on model pricing.

    Thinking tokens count as output tokens for pricing purposes.
    Free-key models, Gemma, and Groq models cost 0.
    """
    prices = DEFAULT_MODEL_PRICES.get(model_id)
    if not prices:
        return 0.0

    input_price = prices.get("input", 0.0)
    output_price = prices.get("output", 0.0)

    if input_price == 0 and output_price == 0:
        return 0.0

    # USD per 1M tokens → USD per token
    cost = (input_tokens * input_price / 1_000_000) + \
           ((output_tokens + thinking_tokens) * output_price / 1_000_000)

    return round(cost, 6)


async def get_account_balance() -> float:
    """Get the current account balance from admin_settings table."""
    row = await fetchrow(
        "SELECT value FROM admin_settings WHERE key = 'account_balance_usd'"
    )
    if row:
        try:
            return float(row["value"])
        except (ValueError, TypeError):
            pass
    return settings.account_balance_usd


async def deduct_balance(cost_usd: float) -> float:
    """
    Subtract cost_usd from the account balance.

    Returns the new balance.
    """
    if cost_usd <= 0:
        return await get_account_balance()

    # Atomic decrement
    row = await fetchrow(
        """UPDATE admin_settings
           SET value = (CAST(value AS DECIMAL) - $1)::TEXT,
               updated_at = NOW()
           WHERE key = 'account_balance_usd'
           RETURNING value""",
        cost_usd,
    )
    if row:
        try:
            return float(row["value"])
        except (ValueError, TypeError):
            pass
    return 0.0


async def get_today_premium_spend() -> float:
    """Get total cost_usd spent today on paid-key (thinking) requests."""
    row = await fetchrow(
        """SELECT COALESCE(SUM(cost_usd), 0) AS total
           FROM query_log
           WHERE thinking_mode = TRUE
             AND created_at >= CURRENT_DATE
             AND cost_usd > 0"""
    )
    return float(row["total"]) if row else 0.0


async def is_premium_enabled() -> bool:
    """Check the PREMIUM_ENABLED admin toggle."""
    row = await fetchrow(
        "SELECT value FROM admin_settings WHERE key = 'premium_enabled'"
    )
    if row:
        return row["value"].lower() in ("true", "1", "yes")
    return settings.premium_enabled


async def check_thinking_conditions(
    user_id: str,
    plan_info: dict,
) -> tuple[bool, str]:
    """
    Check ALL conditions for thinking mode.  Returns ``(ok, reason_code)``.

    Conditions:
      1. PREMIUM_ENABLED is true
      2. User is paid with an active plan
      3. User has thinking credits left today
      4. Today's premium spend is under PREMIUM_DAILY_SPEND_CAP_USD
      5. ACCOUNT_BALANCE_USD is above PREMIUM_MIN_BALANCE_USD
    """
    # 1. Premium enabled
    if not await is_premium_enabled():
        return False, "premium_disabled"

    # 2. User must be paid
    if not plan_info.get("is_paid"):
        return False, "not_paid"

    # 3. Thinking credits left
    daily_limit = plan_info.get("thinking_credits_per_day", 0) or settings.thinking_daily_per_user
    left = await get_thinking_left_today(user_id, daily_limit)
    if left <= 0:
        return False, "daily_limit_reached"

    # 4. Daily premium spend cap
    spend = await get_today_premium_spend()
    if spend >= settings.premium_daily_spend_cap_usd:
        return False, "daily_limit_reached"

    # 5. Balance check
    balance = await get_account_balance()
    if balance < settings.premium_min_balance_usd:
        return False, "balance_low"

    return True, "ok"


# ╔════════════════════════════════════════════════════════════════╗
# ║  Remaining quota                                              ║
# ╚════════════════════════════════════════════════════════════════╝


async def get_remaining(user_id: str) -> dict:
    """
    Return the remaining quota for the current day.

    Dict keys: requests_remaining, tokens_remaining, requests_limit,
    tokens_limit, requests_used, tokens_used, units_used, units_remaining,
    cache_hits_today, plan_name, is_retrieval_only, resets_at,
    thinking_left_today.
    """
    plan = await get_user_plan(user_id)
    usage = await fetchrow(
        """SELECT requests_used, tokens_used, cache_hits, units_used, thinking_credits_used
           FROM usage_daily WHERE user_id = $1 AND date = CURRENT_DATE""",
        user_id,
    )

    requests_used = _row_val(usage, "requests_used", 0)
    tokens_used = _row_val(usage, "tokens_used", 0)
    cache_hits = _row_val(usage, "cache_hits", 0)
    units_used = _row_val(usage, "units_used", requests_used)
    thinking_credits_used = _row_val(usage, "thinking_credits_used", 0)

    req_limit = plan["requests_per_day"]
    tok_limit = plan["tokens_per_day"]
    thinking_daily = plan.get("thinking_credits_per_day", 0) or 0

    # Budget guard check
    retrieval_only = await should_use_retrieval_only(plan["is_paid"])

    # Midnight UTC reset
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        "requests_remaining": max(0, req_limit - units_used),
        "tokens_remaining": max(0, tok_limit - tokens_used),
        "requests_limit": req_limit,
        "tokens_limit": tok_limit,
        "requests_used": requests_used,
        "tokens_used": tokens_used,
        "units_used": units_used,
        "units_remaining": max(0, req_limit - units_used),
        "cache_hits_today": cache_hits,
        "plan_name": plan["plan_name"],
        "is_retrieval_only": retrieval_only,
        "resets_at": tomorrow.isoformat(),
        "thinking_left_today": max(0, thinking_daily - thinking_credits_used),
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

    Uses the rate counter data for today across all free chain models.
    """
    from app.services.rate_counter import get_current_date_str, get_rate_store

    store = get_rate_store()
    date_str = get_current_date_str()

    total_rpd_limit = 0
    total_rpd_used = 0

    # Use free chain for capacity calculation (matches budget guard semantics)
    for model_id in settings.model_chain_free_list:
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
      - Balance guard: paid users switch to retrieval-only when balance
        < PAID_MIN_BALANCE_USD.
    """
    # Balance guard for paid users
    if is_paid:
        try:
            balance = await get_account_balance()
            if balance < settings.paid_min_balance_usd:
                logger.warning(
                    "Balance guard triggered: $%.2f < $%.2f — PAID users → retrieval-only",
                    balance, settings.paid_min_balance_usd,
                )
                return True
        except Exception:
            pass
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
