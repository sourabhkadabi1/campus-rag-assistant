"""
Log every query to the query_log table for analytics.

Fields: user, model used, provider, input/output tokens (from real API
usage metadata), latency, cache hit, route type.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.database import execute

logger = logging.getLogger(__name__)


async def log_query(
    user_id: Optional[str],
    session_id: Optional[str],
    question: str,
    answer: Optional[str] = None,
    model_used: Optional[str] = None,
    provider: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    latency_ms: Optional[int] = None,
    cache_hit: bool = False,
    route_type: str = "llm",
    error: Optional[str] = None,
) -> None:
    """
    Insert a query-log entry.  Fire-and-forget — errors are logged
    but never propagated to the student.
    """
    try:
        await execute(
            """INSERT INTO query_log
               (id, user_id, session_id, question, answer,
                model_used, provider, input_tokens, output_tokens,
                latency_ms, cache_hit, route_type, error)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
            str(uuid.uuid4()),
            user_id,
            session_id,
            question,
            answer[:5000] if answer else None,  # cap stored answer
            model_used,
            provider,
            input_tokens,
            output_tokens,
            latency_ms,
            cache_hit,
            route_type,
            error[:2000] if error else None,
        )
    except Exception as exc:
        logger.warning("Failed to log query: %s", exc)
