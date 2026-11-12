"""
Rate counter and quota tracker for LLM models.

Provides sliding-window tracking for RPM and TPM (past 60s), daily request
counters (RPD) with timezone-aware resets, cooldown management (after 429/5xx),
summary quota reservation, and live model enable/disable toggles.

Supports Redis when REDIS_URL is configured, with a seamless in-memory
fallback for development and testing.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import DEFAULT_MODEL_LIMITS, settings

logger = logging.getLogger(__name__)

# Try to import redis.asyncio
try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


class InMemoryRateStore:
    """Thread-safe / asyncio-safe in-memory rate tracking fallback."""

    def __init__(self):
        self._lock = threading.Lock()
        # model_id -> list of float timestamps (past 60s)
        self._rpm: dict[str, list[float]] = {}
        # model_id -> list of (float timestamp, int tokens) (past 60s)
        self._tpm: dict[str, list[tuple[float, int]]] = {}
        # (model_id, date_str) -> int count
        self._rpd: dict[tuple[str, str], int] = {}
        # (model_id, date_str) -> int tokens
        self._daily_tokens: dict[tuple[str, str], int] = {}
        # model_id -> cooldown expiration timestamp (float)
        self._cooldowns: dict[str, float] = {}
        # model_id -> bool
        self._disabled: set[str] = set()

    def _prune_sliding_windows(self, model_id: str, now: float):
        cutoff = now - 60.0
        if model_id in self._rpm:
            self._rpm[model_id] = [t for t in self._rpm[model_id] if t >= cutoff]
        if model_id in self._tpm:
            self._tpm[model_id] = [
                (t, toks) for t, toks in self._tpm[model_id] if t >= cutoff
            ]

    async def get_rpm(self, model_id: str) -> int:
        with self._lock:
            now = time.time()
            self._prune_sliding_windows(model_id, now)
            return len(self._rpm.get(model_id, []))

    async def get_tpm(self, model_id: str) -> int:
        with self._lock:
            now = time.time()
            self._prune_sliding_windows(model_id, now)
            return sum(toks for _, toks in self._tpm.get(model_id, []))

    async def get_rpd(self, model_id: str, date_str: str) -> int:
        with self._lock:
            return self._rpd.get((model_id, date_str), 0)

    async def get_daily_tokens(self, model_id: str, date_str: str) -> int:
        with self._lock:
            return self._daily_tokens.get((model_id, date_str), 0)

    async def record_request(
        self, model_id: str, date_str: str, estimated_tokens: int = 0
    ):
        with self._lock:
            now = time.time()
            self._prune_sliding_windows(model_id, now)
            self._rpm.setdefault(model_id, []).append(now)
            if estimated_tokens > 0:
                self._tpm.setdefault(model_id, []).append((now, estimated_tokens))
            key = (model_id, date_str)
            self._rpd[key] = self._rpd.get(key, 0) + 1

    async def record_actual_tokens(
        self, model_id: str, date_str: str, actual_tokens: int
    ):
        with self._lock:
            now = time.time()
            self._tpm.setdefault(model_id, []).append((now, actual_tokens))
            key = (model_id, date_str)
            self._daily_tokens[key] = self._daily_tokens.get(key, 0) + actual_tokens

    async def set_cooldown(self, model_id: str, seconds: float):
        with self._lock:
            self._cooldowns[model_id] = time.time() + seconds

    async def get_cooldown_remaining(self, model_id: str) -> float:
        with self._lock:
            expiry = self._cooldowns.get(model_id, 0.0)
            remaining = expiry - time.time()
            return max(0.0, remaining)

    async def clear_cooldown(self, model_id: str):
        with self._lock:
            self._cooldowns.pop(model_id, None)

    async def is_disabled(self, model_id: str) -> bool:
        with self._lock:
            return model_id in self._disabled

    async def set_disabled(self, model_id: str, disabled: bool):
        with self._lock:
            if disabled:
                self._disabled.add(model_id)
            else:
                self._disabled.discard(model_id)

    async def reset(self, model_id: Optional[str] = None):
        with self._lock:
            if model_id:
                self._rpm.pop(model_id, None)
                self._tpm.pop(model_id, None)
                self._cooldowns.pop(model_id, None)
                self._disabled.discard(model_id)
                keys_to_remove = [k for k in self._rpd if k[0] == model_id]
                for k in keys_to_remove:
                    self._rpd.pop(k, None)
                    self._daily_tokens.pop(k, None)
            else:
                self._rpm.clear()
                self._tpm.clear()
                self._rpd.clear()
                self._daily_tokens.clear()
                self._cooldowns.clear()
                self._disabled.clear()


class RedisRateStore:
    """Redis-backed rate tracking store using sorted sets and counters."""

    def __init__(self, redis_client):
        self._redis = redis_client

    async def get_rpm(self, model_id: str) -> int:
        now = time.time()
        cutoff = now - 60.0
        key = f"rag:rpm:{model_id}"
        await self._redis.zremrangebyscore(key, "-inf", cutoff)
        return await self._redis.zcard(key)

    async def get_tpm(self, model_id: str) -> int:
        now = time.time()
        cutoff = now - 60.0
        key = f"rag:tpm:{model_id}"
        await self._redis.zremrangebyscore(key, "-inf", cutoff)
        items = await self._redis.zrange(key, 0, -1)
        total = 0
        for item in items:
            val = item.decode() if isinstance(item, bytes) else str(item)
            try:
                # Format is "{uuid}:{tokens}"
                _, tokens_str = val.split(":", 1)
                total += int(tokens_str)
            except Exception:
                pass
        return total

    async def get_rpd(self, model_id: str, date_str: str) -> int:
        key = f"rag:rpd:{model_id}:{date_str}"
        val = await self._redis.get(key)
        return int(val) if val else 0

    async def get_daily_tokens(self, model_id: str, date_str: str) -> int:
        key = f"rag:daily_tokens:{model_id}:{date_str}"
        val = await self._redis.get(key)
        return int(val) if val else 0

    async def record_request(
        self, model_id: str, date_str: str, estimated_tokens: int = 0
    ):
        now = time.time()
        cutoff = now - 60.0
        req_id = uuid.uuid4().hex[:8]

        # 1. RPM sliding window
        rpm_key = f"rag:rpm:{model_id}"
        await self._redis.zadd(rpm_key, {req_id: now})
        await self._redis.zremrangebyscore(rpm_key, "-inf", cutoff)
        await self._redis.expire(rpm_key, 120)

        # 2. TPM sliding window
        if estimated_tokens > 0:
            tpm_key = f"rag:tpm:{model_id}"
            member = f"{req_id}:{estimated_tokens}"
            await self._redis.zadd(tpm_key, {member: now})
            await self._redis.zremrangebyscore(tpm_key, "-inf", cutoff)
            await self._redis.expire(tpm_key, 120)

        # 3. RPD counter
        rpd_key = f"rag:rpd:{model_id}:{date_str}"
        await self._redis.incr(rpd_key)
        await self._redis.expire(rpd_key, 86400 * 2)

    async def record_actual_tokens(
        self, model_id: str, date_str: str, actual_tokens: int
    ):
        now = time.time()
        cutoff = now - 60.0
        req_id = uuid.uuid4().hex[:8]

        tpm_key = f"rag:tpm:{model_id}"
        member = f"{req_id}:{actual_tokens}"
        await self._redis.zadd(tpm_key, {member: now})
        await self._redis.zremrangebyscore(tpm_key, "-inf", cutoff)
        await self._redis.expire(tpm_key, 120)

        daily_tokens_key = f"rag:daily_tokens:{model_id}:{date_str}"
        await self._redis.incrby(daily_tokens_key, actual_tokens)
        await self._redis.expire(daily_tokens_key, 86400 * 2)

    async def set_cooldown(self, model_id: str, seconds: float):
        key = f"rag:cooldown:{model_id}"
        # Set expiry in seconds (ceil to integer or px)
        ms = int(seconds * 1000)
        await self._redis.set(key, "1", px=ms)

    async def get_cooldown_remaining(self, model_id: str) -> float:
        key = f"rag:cooldown:{model_id}"
        pttl = await self._redis.pttl(key)
        if pttl is None or pttl <= 0:
            return 0.0
        return float(pttl) / 1000.0

    async def clear_cooldown(self, model_id: str):
        key = f"rag:cooldown:{model_id}"
        await self._redis.delete(key)

    async def is_disabled(self, model_id: str) -> bool:
        key = f"rag:disabled:{model_id}"
        val = await self._redis.get(key)
        return bool(val)

    async def set_disabled(self, model_id: str, disabled: bool):
        key = f"rag:disabled:{model_id}"
        if disabled:
            await self._redis.set(key, "1")
        else:
            await self._redis.delete(key)

    async def reset(self, model_id: Optional[str] = None):
        pattern = f"rag:*:{model_id}*" if model_id else "rag:*"
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break


# Global store instance and initialization
_STORE = InMemoryRateStore()
_REDIS_INITIALIZED = False


async def init_rate_store():
    """Initialize Redis connection if configured, else keep in-memory store."""
    global _STORE, _REDIS_INITIALIZED
    if _REDIS_INITIALIZED:
        return

    if HAS_REDIS and settings.redis_url:
        try:
            client = aioredis.from_url(
                settings.redis_url,
                socket_timeout=3.0,
                decode_responses=False,
            )
            # Test ping
            await client.ping()
            _STORE = RedisRateStore(client)
            _REDIS_INITIALIZED = True
            logger.info("✓ Connected to Redis for rate limiting and counters: %s", settings.redis_url)
            return
        except Exception as exc:
            logger.warning("Could not connect to Redis (%s); falling back to in-memory store", exc)

    _STORE = InMemoryRateStore()
    _REDIS_INITIALIZED = True
    logger.info("Using in-memory store for rate counters")


def get_rate_store():
    """Return the active rate store instance."""
    return _STORE


def get_current_date_str() -> str:
    """Return date string YYYY-MM-DD in the configured provider reset timezone."""
    try:
        tz = ZoneInfo(settings.provider_reset_timezone)
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).strftime("%Y-%m-%d")


def get_model_limits(model_id: str) -> dict[str, int]:
    """Get RPM, TPM, RPD limits for a model (with fallback defaults)."""
    if model_id in DEFAULT_MODEL_LIMITS:
        return DEFAULT_MODEL_LIMITS[model_id]

    bare = model_id.removeprefix("groq:")
    if bare in DEFAULT_MODEL_LIMITS:
        return DEFAULT_MODEL_LIMITS[bare]

    # Default conservative limit for unknown models
    return {"rpm": 10, "tpm": 50_000, "rpd": 100}


async def can_use_model(
    model_id: str,
    estimated_tokens: int = 500,
    is_summary_job: bool = False,
) -> tuple[bool, str]:
    """
    Check if a model is currently available to accept a request.

    Returns:
        (can_use, reason)
    """
    store = get_rate_store()

    # 1. Disabled by admin
    if await store.is_disabled(model_id):
        return False, "disabled_by_admin"

    # 2. In cooldown (429 or 5xx)
    cd = await store.get_cooldown_remaining(model_id)
    if cd > 0:
        return False, f"cooldown_{cd:.1f}s"

    limits = get_model_limits(model_id)
    date_str = get_current_date_str()

    # 3. Daily quota check (RPD)
    rpd_used = await store.get_rpd(model_id, date_str)
    rpd_limit = limits["rpd"]

    # SUMMARY_RESERVE_RPD reservation:
    # If the model is used for summaries, student requests cannot touch the reserved quota.
    is_summary_model = model_id in (
        settings.summary_model,
        settings.summary_fallback,
    )
    if is_summary_model and not is_summary_job:
        allowed_rpd = max(1, rpd_limit - settings.summary_reserve_rpd)
    else:
        allowed_rpd = rpd_limit

    # 95% threshold check
    threshold_limit = int(allowed_rpd * settings.router_rpd_threshold_pct)
    if rpd_used >= threshold_limit:
        return False, f"rpd_exhausted_{rpd_used}/{allowed_rpd}"

    # 4. RPM sliding-window check
    rpm_used = await store.get_rpm(model_id)
    if rpm_used >= limits["rpm"]:
        return False, f"rpm_exhausted_{rpm_used}/{limits['rpm']}"

    # 5. TPM sliding-window check
    tpm_used = await store.get_tpm(model_id)
    if tpm_used + estimated_tokens > limits["tpm"]:
        return False, f"tpm_exhausted_{tpm_used}+{estimated_tokens}/{limits['tpm']}"

    return True, "available"


async def record_model_request(
    model_id: str, estimated_tokens: int = 500
):
    """Record an outgoing request against RPM, TPM, and RPD."""
    store = get_rate_store()
    date_str = get_current_date_str()
    await store.record_request(model_id, date_str, estimated_tokens)


async def record_model_usage(
    model_id: str, input_tokens: int, output_tokens: int
):
    """Record actual tokens returned from API metadata."""
    store = get_rate_store()
    date_str = get_current_date_str()
    total_tokens = input_tokens + output_tokens
    await store.record_actual_tokens(model_id, date_str, total_tokens)


async def mark_model_cooldown(model_id: str, status_code: int):
    """Mark a model into cooldown based on status code."""
    store = get_rate_store()
    if status_code == 429:
        cd = float(settings.router_cooldown_429_seconds)
        logger.warning(
            "Model %s received 429 (rate limited). Marking cooldown for %.0fs.",
            model_id, cd,
        )
    elif status_code >= 500:
        cd = float(settings.router_cooldown_5xx_seconds)
        logger.warning(
            "Model %s received %d (server error). Marking cooldown for %.0fs.",
            model_id, status_code, cd,
        )
    else:
        cd = 10.0
    await store.set_cooldown(model_id, cd)


async def get_model_full_status(model_id: str) -> dict:
    """Retrieve complete status and counter metrics for a model."""
    store = get_rate_store()
    date_str = get_current_date_str()
    limits = get_model_limits(model_id)

    rpm = await store.get_rpm(model_id)
    tpm = await store.get_tpm(model_id)
    rpd = await store.get_rpd(model_id, date_str)
    tokens_today = await store.get_daily_tokens(model_id, date_str)
    cooldown = await store.get_cooldown_remaining(model_id)
    disabled = await store.is_disabled(model_id)
    can_use, reason = await can_use_model(model_id)

    is_summary_model = model_id in (
        settings.summary_model,
        settings.summary_fallback,
    )

    return {
        "model_id": model_id,
        "is_enabled": not disabled,
        "is_available": can_use,
        "status_reason": reason,
        "cooldown_remaining_seconds": round(cooldown, 1),
        "rpm_used": rpm,
        "rpm_limit": limits["rpm"],
        "tpm_used": tpm,
        "tpm_limit": limits["tpm"],
        "rpd_used": rpd,
        "rpd_limit": limits["rpd"],
        "tokens_today": tokens_today,
        "is_summary_model": is_summary_model,
        "reserve_rpd": settings.summary_reserve_rpd if is_summary_model else 0,
        "reset_timezone": settings.provider_reset_timezone,
    }


async def toggle_model_enabled(model_id: str, enabled: Optional[bool] = None) -> bool:
    """
    Toggle or set whether a model is enabled.
    Returns the new enabled state (True = enabled, False = disabled).
    """
    store = get_rate_store()
    current_disabled = await store.is_disabled(model_id)
    new_disabled = not enabled if enabled is not None else not current_disabled
    await store.set_disabled(model_id, new_disabled)
    return not new_disabled
