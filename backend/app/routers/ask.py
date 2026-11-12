"""
/ask SSE endpoint — the core query pipeline.

Flow: filter → cache → special routes → QUOTA CHECK → retrieval → LLM → stream → log.

SSE events:
  filter     – parsed filter info
  route      – which route was taken (cache, summary, syllabus, llm)
  token      – streamed answer text (one or more)
  citations  – source citations (final)
  quota      – remaining quota (in done event)
  done       – stream complete
  error      – error occurred
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import fetch, fetchrow
from app.services.answer_cache import (
    CachedAnswer,
    lookup as cache_lookup,
    make_cache_key,
    store as cache_store,
)
from app.services.filter_parser import ParsedQuery, parse_query
from app.services.llm_router import route_and_generate
from app.services.query_logger import log_query
from app.services.retrieval import RetrievalResult, hybrid_search
from app.services.quota import (
    consume_quota,
    get_remaining,
    get_user_plan,
    record_cache_hit,
    record_tokens,
    refund_quota,
    should_use_retrieval_only,
)
from app.services.abuse import check_user_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ask"])


# ── Request model ─────────────────────────────────────────────────


class AskRequest(BaseModel):
    """Body for POST /ask."""
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    detailed: bool = False


# ── Special-route helpers (zero LLM calls) ───────────────────────


async def _serve_chapter_summary(
    chapter_no: int,
    semester: int,
    department: str,
    subject: Optional[str] = None,
) -> Optional[dict]:
    """Serve a stored chapter summary.  Returns None if not found."""
    query = """
        SELECT cs.summary, cs.key_concepts, cs.chapter_no, cs.chapter_title,
               cs.model_used, d.subject
        FROM chapter_summaries cs
        JOIN documents d ON cs.document_id = d.id
        WHERE cs.chapter_no = $1 AND d.semester = $2 AND d.department = $3
              AND d.is_active = TRUE
    """
    args: list = [chapter_no, semester, department]
    idx = 4

    if subject:
        query += f" AND d.subject = ${idx}"
        args.append(subject)

    query += " LIMIT 1"
    row = await fetchrow(query, *args)
    if not row:
        return None

    kc = row["key_concepts"]
    if isinstance(kc, str):
        kc = json.loads(kc)

    return {
        "summary": row["summary"],
        "key_concepts": kc,
        "chapter_no": row["chapter_no"],
        "chapter_title": row["chapter_title"],
        "subject": row["subject"],
        "model_used": row["model_used"],
    }


async def _serve_unit_summary(
    unit_no: int,
    semester: int,
    department: str,
    subject: Optional[str] = None,
) -> Optional[dict]:
    """Serve summaries for all chapters mapped to a unit."""
    map_query = """
        SELECT chapter_no FROM unit_chapter_map
        WHERE unit_no = $1 AND semester = $2 AND department = $3
    """
    args: list = [unit_no, semester, department]
    idx = 4
    if subject:
        map_query += f" AND subject = ${idx}"
        args.append(subject)
    map_query += " ORDER BY chapter_no"

    rows = await fetch(map_query, *args)
    if not rows:
        return None

    summaries = []
    for r in rows:
        s = await _serve_chapter_summary(
            r["chapter_no"], semester, department, subject
        )
        if s:
            summaries.append(s)

    if not summaries:
        return None

    # Combine all chapter summaries under this unit
    combined = f"## Unit {unit_no} Summary\n\n"
    for s in summaries:
        ch_title = f": {s['chapter_title']}" if s.get("chapter_title") else ""
        combined += (
            f"### Chapter {s['chapter_no']}{ch_title}\n\n{s['summary']}\n\n"
        )

    all_concepts: list = []
    for s in summaries:
        if s.get("key_concepts"):
            all_concepts.extend(s["key_concepts"])

    return {
        "summary": combined,
        "key_concepts": all_concepts,
        "subject": summaries[0].get("subject"),
    }


async def _serve_syllabus(
    semester: int,
    department: str,
    subject: Optional[str] = None,
    unit_no: Optional[int] = None,
) -> Optional[str]:
    """Serve syllabus content directly from syllabus chunks."""
    query = """
        SELECT c.content, c.chapter_no, c.unit_no, c.page_start
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.semester = $1 AND d.department = $2
              AND d.doc_type = 'syllabus' AND d.is_active = TRUE
    """
    args: list = [semester, department]
    idx = 3

    if subject:
        query += f" AND d.subject = ${idx}"
        args.append(subject)
        idx += 1

    if unit_no is not None:
        query += f" AND c.unit_no = ${idx}"
        args.append(unit_no)
        idx += 1

    query += " ORDER BY c.chunk_index LIMIT 10"
    rows = await fetch(query, *args)

    if not rows:
        return None

    return "\n\n---\n\n".join(r["content"] for r in rows)


# ── Citation builder ─────────────────────────────────────────────


def _build_citations(chunks: list[RetrievalResult]) -> list[dict]:
    """Build deduplicated citation objects from retrieved chunks."""
    citations: list[dict] = []
    seen: set[tuple] = set()

    for chunk in chunks:
        key = (chunk.subject, chunk.chapter_no, chunk.page_start)
        if key in seen:
            continue
        seen.add(key)
        citations.append({
            "subject": chunk.subject,
            "doc_type": chunk.doc_type,
            "chapter_no": chunk.chapter_no,
            "chapter_title": chunk.chapter_title,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "document_id": chunk.document_id,
        })

    return citations


# ── Main /ask endpoint ───────────────────────────────────────────


@router.post("/ask")
async def ask(request: Request, body: AskRequest):
    """
    Ask a question — returns Server-Sent Events.

    Student identity (semester, department) comes from the authenticated
    profile on the server.  For dev, pass ``X-Semester`` and
    ``X-Department`` headers (replaced by real auth in Phase 4+).
    """
    # ── Student identity (from profile / headers) ─────────
    user_id = request.headers.get("X-User-Id")
    semester_raw = request.headers.get("X-Semester", "0")
    department = request.headers.get("X-Department", "")

    try:
        semester = int(semester_raw)
    except ValueError:
        raise HTTPException(400, "X-Semester must be an integer")

    if not semester or not department:
        raise HTTPException(
            400,
            "Missing student profile.  Set X-Semester and X-Department "
            "headers (auth tokens in production).",
        )

    # ── Per-user per-minute abuse rate limit (Phase 4) ────
    if user_id:
        ok, count = check_user_rate_limit(user_id)
        if not ok:
            raise HTTPException(
                429,
                f"Rate limit exceeded: {count} requests in the last minute. "
                "Please wait before trying again.",
            )

    question = body.question
    session_id = body.session_id
    detailed = body.detailed

    # ── SSE event generator ───────────────────────────────
    async def event_generator():  # noqa: C901 — orchestration is inherently complex
        start_time = time.time()
        route_type = "llm"
        model_used: Optional[str] = None
        provider: Optional[str] = None
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None
        full_answer = ""
        citations: list[dict] = []
        error_msg: Optional[str] = None
        cache_hit = False

        try:
            # ──── 1. Parse filters ────────────────────────
            parsed: ParsedQuery = await parse_query(
                question, semester, department
            )
            yield {
                "event": "filter",
                "data": json.dumps({
                    "subject": parsed.subject,
                    "chapter_no": parsed.chapter_no,
                    "unit_no": parsed.unit_no,
                    "is_summary": parsed.is_summary_request,
                    "is_syllabus": parsed.is_syllabus_request,
                    "clean_query": parsed.clean_query,
                }),
            }

            # Check semester mismatch
            if (
                parsed.mentioned_semester
                and parsed.mentioned_semester != semester
            ):
                msg = (
                    f"You're enrolled in Semester {semester}. "
                    f"I can only search your current semester's materials."
                )
                yield {"event": "token", "data": json.dumps({"text": msg})}
                yield {"event": "done", "data": "{}"}
                route_type = "blocked"
                full_answer = msg
                return

            # ──── 2. Answer cache ─────────────────────────
            cache_key = make_cache_key(question, parsed.subject, semester)
            cached: Optional[CachedAnswer] = await cache_lookup(cache_key)
            if cached:
                cache_hit = True
                route_type = "cache"
                # Cache hits do NOT consume quota
                if user_id:
                    try:
                        await record_cache_hit(user_id)
                    except Exception:
                        pass
                yield {
                    "event": "route",
                    "data": json.dumps({"route": "cache"}),
                }
                yield {
                    "event": "token",
                    "data": json.dumps({"text": cached.answer}),
                }
                if cached.citations:
                    yield {
                        "event": "citations",
                        "data": json.dumps(
                            {"citations": cached.citations}
                        ),
                    }
                full_answer = cached.answer
                yield {"event": "done", "data": "{}"}
                return

            # ──── 3. Special routes (zero LLM) ────────────

            # 3a — Summary / key-concepts request
            if parsed.is_summary_request or parsed.is_key_concepts_request:
                summary_data = None
                if parsed.unit_no:
                    summary_data = await _serve_unit_summary(
                        parsed.unit_no, semester, department, parsed.subject
                    )
                elif parsed.chapter_no:
                    summary_data = await _serve_chapter_summary(
                        parsed.chapter_no, semester, department,
                        parsed.subject,
                    )

                if summary_data:
                    route_type = "summary"
                    yield {
                        "event": "route",
                        "data": json.dumps({"route": "summary"}),
                    }

                    if (
                        parsed.is_key_concepts_request
                        and summary_data.get("key_concepts")
                    ):
                        text = "## Key Concepts\n\n"
                        for kc in summary_data["key_concepts"]:
                            text += f"- {kc}\n"
                    else:
                        text = summary_data["summary"]

                    yield {
                        "event": "token",
                        "data": json.dumps({"text": text}),
                    }
                    full_answer = text

                    # Cache the summary result too
                    try:
                        await cache_store(
                            cache_key, question, text,
                            subject=parsed.subject, semester=semester,
                        )
                    except Exception:
                        pass

                    yield {"event": "done", "data": "{}"}
                    return

            # 3b — Syllabus request
            if parsed.is_syllabus_request:
                syllabus = await _serve_syllabus(
                    semester, department, parsed.subject, parsed.unit_no
                )
                if syllabus:
                    route_type = "syllabus"
                    yield {
                        "event": "route",
                        "data": json.dumps({"route": "syllabus"}),
                    }
                    yield {
                        "event": "token",
                        "data": json.dumps({"text": syllabus}),
                    }
                    full_answer = syllabus
                    try:
                        await cache_store(
                            cache_key, question, syllabus,
                            subject=parsed.subject, semester=semester,
                        )
                    except Exception:
                        pass
                    yield {"event": "done", "data": "{}"}
                    return

            # ──── 4. Quota check (Phase 4) ─────────────────
            #  Happens BEFORE the LLM call. Cache/summary/syllabus
            #  routes above do NOT reach this point (they return early).
            quota_consumed = False
            plan_info: dict = {"plan_name": "free", "is_paid": False,
                               "requests_per_day": 10, "tokens_per_day": 40_000}
            if user_id:
                try:
                    plan_info = await get_user_plan(user_id)
                    ok, usage = await consume_quota(
                        user_id,
                        plan_info["requests_per_day"],
                        plan_info["tokens_per_day"],
                    )
                    if not ok:
                        reason = usage.get("reason", "quota_exceeded")
                        remaining = await get_remaining(user_id)
                        if reason == "tokens_exceeded":
                            msg = (
                                "You've used all your token quota for today. "
                                "Your quota resets at midnight UTC."
                            )
                        else:
                            msg = (
                                "You've used all your questions for today. "
                                "Your quota resets at midnight UTC."
                            )
                        yield {"event": "error", "data": json.dumps({
                            "error": msg, "code": "quota_exceeded",
                        })}
                        yield {"event": "quota", "data": json.dumps(remaining)}
                        yield {"event": "done", "data": "{}"}
                        route_type = "quota_blocked"
                        full_answer = msg
                        error_msg = msg
                        return
                    quota_consumed = True
                except Exception as exc:
                    # Quota service unavailable — allow the request
                    logger.warning("Quota check failed, allowing request: %s", exc)

            # ──── 4b. Budget guard (Phase 4) ──────────────
            #  When combined free-tier capacity is ≥90%, FREE users get
            #  retrieval-only answers.  PAID users are unaffected.
            force_retrieval_only = False
            if user_id:
                try:
                    force_retrieval_only = await should_use_retrieval_only(
                        plan_info.get("is_paid", False)
                    )
                except Exception:
                    pass

            # ──── 5. Hybrid retrieval ─────────────────────
            limit = (
                settings.retrieval_top_k_detailed
                if detailed
                else settings.retrieval_top_k
            )

            chunks, fallback_msg = await hybrid_search(
                query=parsed.clean_query,
                semester=semester,
                department=department,
                subject=parsed.subject,
                chapter_no=parsed.chapter_no,
                unit_chapters=parsed.matched_chapters_from_unit or None,
                limit=limit,
            )

            if fallback_msg:
                prefix = f"\U0001f4cc {fallback_msg}\n\n"
                yield {
                    "event": "token",
                    "data": json.dumps({"text": prefix}),
                }
                full_answer += prefix

            if not chunks:
                text = (
                    "I couldn't find relevant information in your "
                    "course materials for this question."
                )
                yield {
                    "event": "token",
                    "data": json.dumps({"text": text}),
                }
                full_answer = text
                route_type = "not_found"
                yield {"event": "done", "data": "{}"}
                return

            citations = _build_citations(chunks)

            # ──── 5b. Budget guard: retrieval-only for free users ──
            if force_retrieval_only:
                from app.services.llm_router import build_retrieval_fallback
                route_type = "retrieval_only_budget"
                yield {
                    "event": "route",
                    "data": json.dumps({"route": "retrieval_only"}),
                }
                text = (
                    "⚠️ High demand: showing relevant passages directly. "
                    "Upgrade to the Paid plan for AI-generated answers "
                    "during peak times.\n\n"
                    + build_retrieval_fallback(chunks)
                )
                yield {
                    "event": "token",
                    "data": json.dumps({"text": text}),
                }
                full_answer = text
                if citations:
                    yield {
                        "event": "citations",
                        "data": json.dumps({"citations": citations}),
                    }
                # Refund the quota since we didn't actually call an LLM
                if quota_consumed and user_id:
                    try:
                        await refund_quota(user_id, requests=1)
                        quota_consumed = False
                    except Exception:
                        pass
                yield {"event": "done", "data": "{}"}
                return

            # ──── 6. Routed LLM call (Phase 3) ────────────
            yield {
                "event": "route",
                "data": json.dumps({"route": "llm"}),
            }

            # Chat history (last 2 turns)
            history: list[dict] = []
            if session_id:
                try:
                    hist_rows = await fetch(
                        """SELECT role, content FROM chat_messages
                           WHERE session_id = $1
                           ORDER BY created_at DESC LIMIT 4""",
                        session_id,
                    )
                    history = [
                        {"role": r["role"], "content": r["content"]}
                        for r in reversed(hist_rows)
                    ]
                except Exception:
                    pass

            # Use the Phase 3 router — walks MODEL_CHAIN, handles
            # fallback, queuing, prompt budgeting, and rate limits.
            async for event in route_and_generate(
                chunks=chunks,
                question=parsed.clean_query,
                history=history,
                detailed=detailed,
            ):
                if event["type"] == "model_selected":
                    model_used = event["model_id"]
                    provider = event["provider"]
                elif event["type"] == "token":
                    yield {
                        "event": "token",
                        "data": json.dumps({"text": event["text"]}),
                    }
                    full_answer += event["text"]
                elif event["type"] == "usage":
                    input_tokens = event.get("input_tokens")
                    output_tokens = event.get("output_tokens")
                elif event["type"] == "queue_position":
                    yield {
                        "event": "queue",
                        "data": json.dumps({
                            "position": event["position"],
                            "estimated_seconds": event.get(
                                "estimated_seconds"
                            ),
                        }),
                    }
                elif event["type"] == "retrieval_fallback":
                    yield {
                        "event": "token",
                        "data": json.dumps({"text": event["text"]}),
                    }
                    full_answer += event["text"]
                    route_type = "retrieval_fallback"
                elif event["type"] == "error":
                    error_msg = event.get("text", "Unknown error")
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": error_msg}),
                    }
                elif event["type"] == "rate_limited":
                    # Router handles retry internally; this only fires
                    # if the entire chain is exhausted.
                    error_msg = "All models rate-limited"
                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "error": "All models are currently "
                            "rate-limited. Please try again shortly."
                        }),
                    }

            # Send citations as a final event
            if citations:
                yield {
                    "event": "citations",
                    "data": json.dumps({"citations": citations}),
                }

            # Record real token usage from API response (Phase 4)
            if user_id and input_tokens is not None and output_tokens is not None:
                total_tokens = (input_tokens or 0) + (output_tokens or 0)
                if total_tokens > 0:
                    try:
                        await record_tokens(user_id, total_tokens)
                    except Exception:
                        pass

            # Cache the answer
            if full_answer and not error_msg:
                try:
                    await cache_store(
                        cache_key, question, full_answer, citations,
                        subject=parsed.subject, semester=semester,
                    )
                except Exception as exc:
                    logger.warning("Failed to cache answer: %s", exc)

            # Emit remaining quota in the done event (Phase 4)
            quota_data = {}
            if user_id:
                try:
                    quota_data = await get_remaining(user_id)
                except Exception:
                    pass

            yield {
                "event": "done",
                "data": json.dumps({"quota": quota_data} if quota_data else {}),
            }

        except Exception as exc:
            logger.exception("Error in /ask: %s", exc)
            error_msg = str(exc)
            yield {
                "event": "error",
                "data": json.dumps(
                    {"error": "An internal error occurred."}
                ),
            }

            # Refund quota on LLM failure (Phase 4)
            if quota_consumed and user_id:
                try:
                    await refund_quota(user_id, requests=1)
                    quota_consumed = False
                except Exception:
                    pass

        finally:
            # ──── 7. Log every request ────────────────────
            latency_ms = int((time.time() - start_time) * 1000)
            try:
                await log_query(
                    user_id=user_id,
                    session_id=session_id,
                    question=question,
                    answer=full_answer[:5000] if full_answer else None,
                    model_used=model_used,
                    provider=provider,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    cache_hit=cache_hit,
                    route_type=route_type,
                    error=error_msg,
                )
            except Exception as exc:
                logger.warning("Failed to log query: %s", exc)

    return EventSourceResponse(event_generator())
