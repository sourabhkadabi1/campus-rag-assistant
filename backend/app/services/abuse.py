"""
Abuse protection — per-user rate limiting, email verification, bot protection.

Layered defences:
  1. Per-user per-minute rate limit (in-memory or Redis, same store as model rate counters).
  2. One account per college email / roll number (enforced by DB unique constraints).
  3. Email verification tokens.
  4. Request size limits (already enforced by Pydantic ``max_length``).
  5. Basic bot protection via honeypot and timing checks.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.database import execute, fetchrow

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Per-user per-minute rate limiter                             ║
# ╚════════════════════════════════════════════════════════════════╝


class UserRateLimiter:
    """
    Sliding-window rate limiter for per-user per-minute limits.

    Thread-safe via a simple lock.  For multi-process deployments
    this should be backed by Redis (same pattern as ``rate_counter``).
    """

    def __init__(self):
        self._lock = threading.Lock()
        # user_id -> list of float timestamps (within the last 60s)
        self._requests: dict[str, list[float]] = {}

    def _prune(self, user_id: str, now: float) -> None:
        cutoff = now - 60.0
        if user_id in self._requests:
            self._requests[user_id] = [
                t for t in self._requests[user_id] if t >= cutoff
            ]

    def check_and_record(self, user_id: str, limit: int | None = None) -> tuple[bool, int]:
        """
        Check whether *user_id* may proceed, and if so, record the request.

        Returns ``(ok, current_count)`` where *ok* is False when the
        per-minute limit has been reached.
        """
        rpm_limit = limit or settings.user_rpm_limit
        now = time.time()

        with self._lock:
            self._prune(user_id, now)
            current = len(self._requests.get(user_id, []))

            if current >= rpm_limit:
                return False, current

            self._requests.setdefault(user_id, []).append(now)
            return True, current + 1

    def get_count(self, user_id: str) -> int:
        """Return the current request count within the sliding window."""
        now = time.time()
        with self._lock:
            self._prune(user_id, now)
            return len(self._requests.get(user_id, []))

    def reset(self, user_id: Optional[str] = None) -> None:
        """Reset rate data (for testing)."""
        with self._lock:
            if user_id:
                self._requests.pop(user_id, None)
            else:
                self._requests.clear()


# Global singleton
_limiter = UserRateLimiter()


def get_limiter() -> UserRateLimiter:
    """Return the global rate limiter instance."""
    return _limiter


def check_user_rate_limit(user_id: str) -> tuple[bool, int]:
    """
    Check per-user per-minute rate limit.

    Returns ``(ok, count)``.  When ``ok`` is False the user should
    receive HTTP 429.
    """
    return _limiter.check_and_record(user_id)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Email verification                                           ║
# ╚════════════════════════════════════════════════════════════════╝


def generate_verification_token() -> str:
    """Generate a secure random verification token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)


async def create_verification(user_id: str) -> str:
    """
    Create an email verification token for *user_id*.

    Stores the token and expiry in the profiles table.
    Returns the token (caller should email it to the user).
    """
    token = generate_verification_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    await execute(
        """UPDATE profiles
           SET verification_token = $1, verification_expires_at = $2,
               updated_at = NOW()
           WHERE id = $3""",
        token, expires, user_id,
    )
    return token


async def verify_email(token: str) -> dict:
    """
    Verify an email using the provided token.

    Returns ``{ok: True, user_id: ...}`` on success, or
    ``{ok: False, reason: ...}`` on failure.
    """
    row = await fetchrow(
        """SELECT id, email, email_verified, verification_expires_at
           FROM profiles WHERE verification_token = $1""",
        token,
    )

    if not row:
        return {"ok": False, "reason": "invalid_token"}

    if row["email_verified"]:
        return {"ok": True, "user_id": str(row["id"]), "already_verified": True}

    if row["verification_expires_at"] and row["verification_expires_at"] < datetime.now(timezone.utc):
        return {"ok": False, "reason": "token_expired"}

    await execute(
        """UPDATE profiles
           SET email_verified = TRUE, verification_token = NULL,
               verification_expires_at = NULL, updated_at = NOW()
           WHERE id = $1""",
        row["id"],
    )

    return {"ok": True, "user_id": str(row["id"])}


# ╔════════════════════════════════════════════════════════════════╗
# ║  Bot protection helpers                                       ║
# ╚════════════════════════════════════════════════════════════════╝


def check_honeypot(honeypot_value: Optional[str]) -> bool:
    """
    Basic honeypot check for signup forms.

    A hidden field should be left empty by real users.
    Returns True if the request looks human (field empty or None).
    """
    return not honeypot_value


def check_timing(form_loaded_at: Optional[float]) -> bool:
    """
    Basic timing check for signup forms.

    If the form was submitted in under 2 seconds, it's likely a bot.
    Returns True if the timing looks human.
    """
    if form_loaded_at is None:
        return True  # No timing info — allow

    elapsed = time.time() - form_loaded_at
    return elapsed >= 2.0
