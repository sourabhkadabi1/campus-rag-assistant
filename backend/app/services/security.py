"""
Security utilities — authentication, input sanitization, prompt-injection defense.

Phase 6: Centralised security helpers used across all routers.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
import unicodedata
from typing import Optional

from fastapi import HTTPException, Request

from app.config import settings
from app.database import fetchrow

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Admin Authentication (shared by all admin routers)           ║
# ╚════════════════════════════════════════════════════════════════╝


def create_admin_token(timestamp: int) -> str:
    """Generate an HMAC-signed admin session token."""
    payload = f"{settings.admin_username}:{timestamp}"
    signature = hmac.new(
        settings.admin_password.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{timestamp}.{signature}"


async def require_admin(request: Request) -> None:
    """
    FastAPI dependency — rejects non-admin requests with HTTP 401.

    Validates the signed Bearer token created by POST /admin/authenticate.
    Token is valid for 8 hours.
    """
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    try:
        timestamp_text, signature = token.split(".", 1)
        timestamp = int(timestamp_text)
    except (ValueError, AttributeError):
        raise HTTPException(401, "Administrator authentication required")

    if (
        not settings.admin_username
        or not settings.admin_password
        or abs(int(time.time()) - timestamp) > 8 * 60 * 60
    ):
        raise HTTPException(401, "Administrator session expired")

    expected = create_admin_token(timestamp).split(".", 1)[1]
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Administrator authentication required")


# ╔════════════════════════════════════════════════════════════════╗
# ║  Upload / Input Sanitization                                  ║
# ╚════════════════════════════════════════════════════════════════╝


PDF_MAGIC = b"%PDF-"


def validate_pdf_bytes(content: bytes) -> bool:
    """
    Return True if *content* starts with the PDF magic header (%PDF-).

    This is a defence-in-depth check: an attacker who renames an
    image or executable to .pdf is rejected here.
    """
    return len(content) >= 5 and content[:5] == PDF_MAGIC


def sanitize_filename(filename: str) -> str:
    """
    Strip path components and dangerous characters from an uploaded filename.

    Prevents directory-traversal attacks (../../etc/passwd) and
    control-character injection.
    """
    # Remove any directory components (both Unix and Windows separators)
    name = filename.replace("\\", "/").split("/")[-1]
    # Strip null bytes and control characters
    name = "".join(
        ch for ch in name
        if ch in ("\n", "\r", "\t") or unicodedata.category(ch)[0] != "C"
    )
    # Allow only safe characters: alphanumerics, dots, hyphens, underscores, spaces
    name = re.sub(r"[^a-zA-Z0-9_.\-\s]", "_", name)
    # Collapse runs of underscores / spaces
    name = re.sub(r"[_\s]+", "_", name).strip("_")
    return name or "unnamed.pdf"


def sanitize_text_input(text: str, max_length: int = 2000) -> str:
    """Strip control characters and clamp length for user-facing text inputs."""
    cleaned = "".join(
        ch for ch in text
        if ch in ("\n", "\r", "\t") or unicodedata.category(ch)[0] != "C"
    )
    return cleaned[:max_length]


def validate_metadata_field(value: str, field_name: str, max_len: int = 100) -> str:
    """
    Validate and sanitize a metadata field (department, subject, academic_year).

    Raises HTTPException(422) if the value contains dangerous characters.
    """
    if not value or not value.strip():
        raise HTTPException(422, f"'{field_name}' must not be empty")
    cleaned = sanitize_text_input(value.strip(), max_length=max_len)
    # Reject strings that look like SQL injection or path traversal
    dangerous = re.search(r"[;<>|&`$\\]|\.{2,}", cleaned)
    if dangerous:
        raise HTTPException(422, f"'{field_name}' contains invalid characters")
    return cleaned


# ╔════════════════════════════════════════════════════════════════╗
# ║  Prompt-Injection Detection                                   ║
# ╚════════════════════════════════════════════════════════════════╝


_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|prompts?)",
        re.IGNORECASE,
    ),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(
        r"(reveal|show|output|print|display)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"forget\s+(everything|all|your)\s+(you|instructions?|rules?)",
        re.IGNORECASE,
    ),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a)\s+", re.IGNORECASE),
    re.compile(
        r"(bypass|override|disable)\s+(your\s+)?(safety|security|filter|restriction)",
        re.IGNORECASE,
    ),
    re.compile(
        r"do\s+not\s+follow\s+(your|the)\s+(instructions?|rules?|guidelines?)",
        re.IGNORECASE,
    ),
    re.compile(r"\bDAN\b.*\bmode\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
]


def detect_injection_markers(text: str) -> bool:
    """
    Heuristic check for prompt-injection patterns in a user question.

    Returns True if adversarial patterns are detected.  Used for
    *logging and monitoring* — the system prompt also defends at the
    model level, so this is a defence-in-depth layer.
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ╔════════════════════════════════════════════════════════════════╗
# ║  Session Ownership Verification                               ║
# ╚════════════════════════════════════════════════════════════════╝


async def verify_session_ownership(session_id: str, user_id: str) -> dict:
    """
    Verify that *session_id* belongs to *user_id*.

    Returns the session row dict on success.
    Raises HTTPException(404) if not found, 403 if owned by another user.
    """
    row = await fetchrow(
        "SELECT id, user_id, title, subject, created_at, updated_at "
        "FROM chat_sessions WHERE id = $1",
        session_id,
    )
    if not row:
        raise HTTPException(404, "Session not found")
    if str(row["user_id"]) != user_id:
        raise HTTPException(
            403, "Access denied — this session belongs to another user"
        )
    return dict(row)


async def get_server_profile(user_id: str) -> Optional[dict]:
    """
    Look up a user profile from the database by ID.

    Returns None if the profile does not exist (browser-generated UUID
    without a corresponding server record).
    """
    row = await fetchrow(
        """SELECT id, email, role, department, semester, roll_no,
                  plan_id, plan_expires_at
           FROM profiles WHERE id = $1""",
        user_id,
    )
    return dict(row) if row else None
