"""
Answer cache — normalised question hash, lookup, store, TTL.

Cache key = SHA-256(normalised_question | semester | subject | academic_year).
Cache hits never consume student quota.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.database import execute, fetchrow

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Data class                                                   ║
# ╚════════════════════════════════════════════════════════════════╝


@dataclass
class CachedAnswer:
    """A cached answer retrieved from the database."""
    answer: str
    citations: Optional[list[dict]]
    question: str
    hit_count: int


# ╔════════════════════════════════════════════════════════════════╗
# ║  Normalisation & key generation                               ║
# ╚════════════════════════════════════════════════════════════════╝


def normalize_question(question: str) -> str:
    """
    Normalise a question for cache-key generation.
    Strips case, punctuation, filler words, extra whitespace.
    """
    q = question.lower().strip()
    q = re.sub(r"[^\w\s]", "", q)           # remove punctuation
    q = re.sub(r"\s+", " ", q)              # collapse whitespace
    # Remove common filler phrases
    for filler in ("please", "can you", "could you", "tell me about",
                    "tell me", "i want to know"):
        q = q.replace(filler, "")
    return re.sub(r"\s+", " ", q).strip()


def make_cache_key(
    question: str,
    subject: Optional[str],
    semester: int,
    academic_year: Optional[str] = None,
) -> str:
    """Generate a deterministic cache key from question + context."""
    normalised = normalize_question(question)
    parts = [normalised, str(semester)]
    if subject:
        parts.append(subject.lower().strip())
    if academic_year:
        parts.append(academic_year.strip())
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ╔════════════════════════════════════════════════════════════════╗
# ║  Lookup & store                                               ║
# ╚════════════════════════════════════════════════════════════════╝


async def lookup(cache_key: str) -> Optional[CachedAnswer]:
    """
    Look up a cached answer.  Returns ``None`` on miss.
    Increments hit_count on every successful lookup.
    """
    row = await fetchrow(
        """SELECT question, answer, citations, hit_count
           FROM answer_cache
           WHERE cache_key = $1
             AND (expires_at IS NULL OR expires_at > NOW())""",
        cache_key,
    )
    if not row:
        return None

    # Fire-and-forget hit-count bump
    try:
        await execute(
            "UPDATE answer_cache SET hit_count = hit_count + 1 WHERE cache_key = $1",
            cache_key,
        )
    except Exception:
        pass  # non-critical

    citations = row["citations"]
    if isinstance(citations, str):
        citations = json.loads(citations)

    return CachedAnswer(
        answer=row["answer"],
        citations=citations,
        question=row["question"],
        hit_count=row["hit_count"] + 1,
    )


async def store(
    cache_key: str,
    question: str,
    answer: str,
    citations: Optional[list[dict]] = None,
    subject: Optional[str] = None,
    semester: Optional[int] = None,
    academic_year: Optional[str] = None,
    ttl_hours: Optional[int] = None,
) -> None:
    """Store an answer in the cache (upsert)."""
    ttl = ttl_hours if ttl_hours is not None else settings.cache_ttl_hours
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=ttl) if ttl > 0 else None
    )

    await execute(
        """INSERT INTO answer_cache
           (id, cache_key, question, answer, citations,
            subject, semester, academic_year, expires_at)
           VALUES (gen_random_uuid(), $1, $2, $3, $4::jsonb,
                   $5, $6, $7, $8)
           ON CONFLICT (cache_key) DO UPDATE
           SET answer = $3, citations = $4::jsonb,
               expires_at = $8, hit_count = 0""",
        cache_key, question, answer,
        json.dumps(citations) if citations else None,
        subject, semester, academic_year, expires_at,
    )
