"""
LLM Router — walks the MODEL_CHAIN, picks the first available model,
handles prompt budgeting, streaming, failover, and request queuing.

Core routing logic for Phase 3:
- Checks each model in priority order for availability (cooldown, RPM/TPM/RPD).
- Shrinks prompts for models with small TPM (Gemma ~16K, Groq ~8K).
- On 429/5xx: marks cooldown, retries next model immediately.
- If all models busy: queues the request with exponential backoff,
  pushing queue-position updates over SSE.  Timeout → retrieval-only fallback.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator

from app.config import settings
from app.services.llm_caller import generate_answer, get_provider
from app.services.model_verifier import get_verified_active_chain, is_model_verified
from app.services.rate_counter import (
    can_use_model,
    get_model_limits,
    mark_model_cooldown,
    record_model_request,
    record_model_usage,
)
from app.services.retrieval import RetrievalResult

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Prompt budgeting                                             ║
# ╚════════════════════════════════════════════════════════════════╝


def budget_prompt(
    model_id: str,
    chunks: list[RetrievalResult],
    history: list[dict] | None,
    max_output_tokens: int,
) -> tuple[list[RetrievalResult], list[dict] | None, int]:
    """
    Trim chunks, history, and max_output_tokens for models with small TPM.

    Thresholds:
      - TPM ≤ 8 000  → 1 chunk, no history, max 300 output tokens.
      - TPM ≤ 16 000 → 2 chunks, 1 turn (2 msgs), max 400 output tokens.
      - Otherwise    → pass through unchanged.

    Returns:
        ``(trimmed_chunks, trimmed_history, adjusted_max_output_tokens)``
    """
    limits = get_model_limits(model_id)
    tpm = limits.get("tpm", 250_000)

    if tpm <= 8_000:
        # Very constrained (e.g. Groq ~8K TPM) — 1 chunk, no history
        trimmed_chunks = chunks[:1]
        trimmed_history = None
        adjusted_max = min(300, max_output_tokens)
        logger.debug(
            "Budget[%s]: TPM=%d → 1 chunk, no history, max_out=%d",
            model_id, tpm, adjusted_max,
        )
    elif tpm <= 16_000:
        # Medium constraint (e.g. Gemma ~16K TPM) — 2 chunks, 1 turn
        trimmed_chunks = chunks[:2]
        # Keep last 1 turn = 2 messages (user + assistant)
        trimmed_history = (history or [])[-2:] or None
        adjusted_max = min(400, max_output_tokens)
        logger.debug(
            "Budget[%s]: TPM=%d → 2 chunks, 1 turn, max_out=%d",
            model_id, tpm, adjusted_max,
        )
    else:
        # Large TPM — pass through unchanged
        trimmed_chunks = chunks
        trimmed_history = history
        adjusted_max = max_output_tokens

    return trimmed_chunks, trimmed_history, adjusted_max


# ╔════════════════════════════════════════════════════════════════╗
# ║  Retrieval fallback                                           ║
# ╚════════════════════════════════════════════════════════════════╝


def build_retrieval_fallback(chunks: list[RetrievalResult]) -> str:
    """
    Format retrieved chunks into a readable text answer with citations.

    Used when all LLM models are exhausted or timed out.
    """
    header = (
        "⚠️ All AI models are currently at capacity. "
        "Here are the most relevant passages from your course materials:"
    )
    if not chunks:
        return f"{header}\n\nNo relevant passages were found."

    parts: list[str] = [header, ""]
    for i, chunk in enumerate(chunks, 1):
        source = chunk.doc_type.title() if chunk.doc_type else "Document"
        ch = f", Chapter {chunk.chapter_no}" if chunk.chapter_no else ""
        pg = (
            f", Pages {chunk.page_start}–{chunk.page_end}"
            if chunk.page_start
            else ""
        )
        citation = f"[Source {i}: {chunk.subject} {source}{ch}{pg}]"
        parts.append(f"### {citation}")
        parts.append(chunk.content)
        parts.append("")  # blank line between chunks

    return "\n".join(parts)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Model selection helpers                                      ║
# ╚════════════════════════════════════════════════════════════════╝


async def _pick_model(
    chain: list[str],
    estimated_tokens: int,
    is_summary_job: bool,
    skip: set[str] | None = None,
) -> tuple[str | None, str | None]:
    """
    Walk *chain* and return the first available ``(model_id, None)`` pair.

    If no model is available, returns ``(None, last_reject_reason)``.

    Args:
        chain: Ordered list of model IDs to try.
        estimated_tokens: Rough token estimate for TPM check.
        is_summary_job: Whether this request is a summary generation.
        skip: Model IDs to exclude (already failed this request).
    """
    skip = skip or set()
    last_reason = "no_models_in_chain"

    for model_id in chain:
        if model_id in skip:
            continue
        ok, reason = await can_use_model(model_id, estimated_tokens, is_summary_job)
        if ok:
            return model_id, None
        last_reason = reason
        logger.debug("Model %s unavailable: %s", model_id, reason)

    return None, last_reason


def _estimate_tokens(
    chunks: list[RetrievalResult],
    history: list[dict] | None,
) -> int:
    """Rough token estimate for rate-counter checks (~1 token ≈ 4 chars)."""
    total_chars = sum(len(c.content) for c in chunks)
    if history:
        total_chars += sum(len(m.get("content", "")) for m in history)
    # Add overhead for system prompt + question formatting
    return max(200, total_chars // 4 + 300)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Main public interface                                        ║
# ╚════════════════════════════════════════════════════════════════╝


async def route_and_generate(
    chunks: list[RetrievalResult],
    question: str,
    history: list[dict] | None,
    detailed: bool,
    is_summary_job: bool = False,
) -> AsyncGenerator[dict, None]:
    """
    Select a model, budget the prompt, and stream the LLM answer.

    This is the main entry point for the LLM router.  It yields event
    dicts that are a superset of ``llm_caller.generate_answer``:

    - ``{"type": "model_selected", "model_id": "...", "provider": "..."}``
    - ``{"type": "queue_position", "position": N, "estimated_seconds": M}``
    - ``{"type": "token", "text": "..."}``
    - ``{"type": "usage", "input_tokens": N, "output_tokens": M}``
    - ``{"type": "error", "text": "..."}``
    - ``{"type": "rate_limited", "status": 429}``
    - ``{"type": "retrieval_fallback", "text": "..."}``

    Args:
        chunks: Retrieved context chunks.
        question: The student's question.
        history: Conversation history (list of role/content dicts).
        detailed: If True, use the higher max_output_tokens setting.
        is_summary_job: If True, this request counts against summary quota.
    """
    max_out = (
        settings.max_output_tokens_detailed if detailed
        else settings.max_output_tokens
    )
    estimated_tokens = _estimate_tokens(chunks, history)
    chain = get_verified_active_chain()

    if not chain:
        logger.error("No models in verified active chain — serving fallback")
        yield {
            "type": "retrieval_fallback",
            "text": build_retrieval_fallback(chunks),
        }
        return

    # Delegate to the inner generator that handles failover + queuing
    async for event in _attempt_with_failover(
        chain, chunks, question, history, max_out,
        estimated_tokens, is_summary_job,
    ):
        yield event


# ╔════════════════════════════════════════════════════════════════╗
# ║  Internal: failover loop + queue mode                         ║
# ╚════════════════════════════════════════════════════════════════╝


async def _attempt_with_failover(
    chain: list[str],
    chunks: list[RetrievalResult],
    question: str,
    history: list[dict] | None,
    max_out: int,
    estimated_tokens: int,
    is_summary_job: bool,
) -> AsyncGenerator[dict, None]:
    """
    Phase 1 — try models in order; on retryable failure, skip and continue.
    Phase 2 — queue with exponential backoff when all models are busy.
    """
    failed_models: set[str] = set()

    # ── Phase 1: immediate model selection ──────────────────────────
    while True:
        model_id, _ = await _pick_model(
            chain, estimated_tokens, is_summary_job, skip=failed_models,
        )
        if model_id is None:
            break  # → queue mode

        should_retry = False
        async for event in _stream_from_model(
            model_id, chunks, question, history,
            max_out, estimated_tokens,
        ):
            if event.get("type") == "__retry__":
                failed_models.add(model_id)
                should_retry = True
                break
            yield event

        if not should_retry:
            return  # success — stream completed

        # Loop to try the next model in chain

    # ── Phase 2: queue mode (exponential backoff) ──────────────────
    async for event in _queue_loop(
        chain, chunks, question, history,
        max_out, estimated_tokens, is_summary_job,
    ):
        yield event


async def _stream_from_model(
    model_id: str,
    chunks: list[RetrievalResult],
    question: str,
    history: list[dict] | None,
    max_out: int,
    estimated_tokens: int,
) -> AsyncGenerator[dict, None]:
    """
    Budget, record, and stream from a single model.

    On success: yields normal events (token, usage, model_selected, …).
    On retryable failure (429 / 5xx): yields ``{"type": "__retry__"}``
    sentinel and returns.
    """
    # Apply prompt budgeting
    trimmed_chunks, trimmed_history, adj_max = budget_prompt(
        model_id, chunks, history, max_out,
    )

    provider = get_provider(model_id)
    logger.info(
        "Router → model=%s provider=%s est_tokens=%d max_out=%d",
        model_id, provider, estimated_tokens, adj_max,
    )
    yield {"type": "model_selected", "model_id": model_id, "provider": provider}

    # Pre-record the request against rate counters
    await record_model_request(model_id, estimated_tokens)

    async for event in generate_answer(
        model_id, trimmed_chunks, question, trimmed_history, adj_max,
    ):
        etype = event["type"]

        # ── Rate-limited (429) ──
        if etype == "rate_limited":
            status = event.get("status", 429)
            logger.warning(
                "Model %s returned %d during stream — failing over",
                model_id, status,
            )
            await mark_model_cooldown(model_id, status)
            yield {"type": "__retry__"}
            return

        # ── Error — check if retryable (5xx) ──
        if etype == "error":
            text = event.get("text", "")
            is_5xx = _is_server_error(text)
            if is_5xx:
                logger.warning(
                    "Model %s → 5xx error — failing over: %s",
                    model_id, text[:120],
                )
                await mark_model_cooldown(model_id, 500)
                yield {"type": "__retry__"}
                return
            # Non-retryable error — surface to caller
            yield event
            return

        # ── Usage metadata — record actual consumption ──
        if etype == "usage":
            await record_model_usage(
                model_id,
                event.get("input_tokens", 0),
                event.get("output_tokens", 0),
            )

        # Forward event (token, usage, etc.)
        yield event


def _is_server_error(error_text: str) -> bool:
    """Check whether an error message indicates a 5xx server error."""
    for code in range(500, 600):
        marker = str(code)
        # Match patterns like "Gemini 500:" or "Groq 503:"
        if f" {marker}:" in error_text or f" {marker} " in error_text:
            return True
    return False


async def _queue_loop(
    chain: list[str],
    chunks: list[RetrievalResult],
    question: str,
    history: list[dict] | None,
    max_out: int,
    estimated_tokens: int,
    is_summary_job: bool,
) -> AsyncGenerator[dict, None]:
    """
    Wait for a model to become available with exponential backoff.

    Yields ``queue_position`` events while waiting.
    On timeout, yields ``retrieval_fallback``.
    """
    timeout = settings.router_queue_timeout_seconds
    backoff = 0.5
    start = time.monotonic()
    position = 1

    logger.info(
        "All models busy — entering queue (timeout=%ds, chain_len=%d)",
        timeout, len(chain),
    )

    while True:
        elapsed = time.monotonic() - start
        remaining = timeout - elapsed
        if remaining <= 0:
            break

        # Tell the client where they are in the queue
        est_seconds = min(int(backoff * 2), int(remaining))
        yield {
            "type": "queue_position",
            "position": position,
            "estimated_seconds": max(1, est_seconds),
        }

        # Sleep (but don't overshoot the timeout)
        await asyncio.sleep(min(backoff, remaining))

        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            break

        # Re-check the full chain (cooldowns may have expired)
        model_id, _ = await _pick_model(
            chain, estimated_tokens, is_summary_job,
        )
        if model_id is not None:
            logger.info(
                "Model %s available after %.1fs in queue", model_id, elapsed,
            )
            success = True
            async for event in _stream_from_model(
                model_id, chunks, question, history,
                max_out, estimated_tokens,
            ):
                if event.get("type") == "__retry__":
                    success = False
                    break
                yield event

            if success:
                return

            # Model failed during queue retry — continue waiting
            logger.debug(
                "Model %s failed during queue retry — continuing backoff",
                model_id,
            )

        # Exponential backoff: 0.5 → 1 → 2 → 4 → 8 (capped)
        backoff = min(backoff * 2, 8.0)
        position = max(1, position)  # position stays at 1 for single-user

    # ── Timeout reached — serve chunks directly ──
    logger.warning(
        "Queue timeout after %ds — serving retrieval-only fallback", timeout,
    )
    yield {
        "type": "retrieval_fallback",
        "text": build_retrieval_fallback(chunks),
    }
