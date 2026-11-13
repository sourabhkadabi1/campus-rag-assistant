"""
LLM call wrapper — Gemini and Groq adapters with SSE streaming.

Exactly ONE LLM call per uncached question.
One short shared system prompt for ALL models.
If a model handles system prompts poorly (Gemma), the system text is
prepended to the user message instead.

Supports dual API keys (free/paid) via the `api_key` parameter
and Gemini thinking mode via `thinking_config`.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from app.config import settings
from app.services.retrieval import RetrievalResult

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Shared system prompt (used by ALL models)                    ║
# ╚════════════════════════════════════════════════════════════════╝

SYSTEM_PROMPT = """\
You are a college course assistant. Answer ONLY from the provided context.

Rules:
- Cite sources as [Book/Notes, Chapter N, Page M].
- If the context is insufficient, say: "I couldn't find this in your course material."
- NEVER invent or guess citations.
- Be concise and exam-friendly.
- Render equations and formulas in LaTeX.
- Use bullet points and numbered lists for clarity.
- Do not include information not present in the context."""

# Models that don't support a dedicated system role —
# the system text is prepended to the first user message instead.
MODELS_WITHOUT_SYSTEM_ROLE = {"gemma-4-26b", "gemma-4-31b"}


# ╔════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                      ║
# ╚════════════════════════════════════════════════════════════════╝


def get_provider(model_id: str) -> str:
    """Determine the API provider from a model ID."""
    return "groq" if model_id.startswith("groq:") else "gemini"


def build_context_block(chunks: list[RetrievalResult]) -> str:
    """Format retrieved chunks into a numbered context block."""
    if not chunks:
        return "[No relevant context found]"

    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.doc_type.title() if chunk.doc_type else "Document"
        ch = f", Chapter {chunk.chapter_no}" if chunk.chapter_no else ""
        pg = (
            f", Pages {chunk.page_start}–{chunk.page_end}"
            if chunk.page_start
            else ""
        )
        header = f"[Source {i}: {chunk.subject} {source}{ch}{pg}]"
        parts.append(f"{header}\n{chunk.content}")

    return "\n\n---\n\n".join(parts)


def build_messages(
    question: str,
    chunks: list[RetrievalResult],
    history: list[dict] | None = None,
    model_id: str = "",
) -> list[dict]:
    """Build the message list for the LLM call."""
    context = build_context_block(chunks)
    user_msg = f"Context:\n{context}\n\nQuestion: {question}"

    messages: list[dict] = []

    # System prompt handling — Gemma gets it prepended to the user msg
    bare_id = model_id.removeprefix("groq:")
    if bare_id in MODELS_WITHOUT_SYSTEM_ROLE:
        user_msg = f"{SYSTEM_PROMPT}\n\n{user_msg}"
    else:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # Last 2 chat turns = 4 messages (user + assistant each)
    if history:
        for msg in history[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_msg})
    return messages


# ╔════════════════════════════════════════════════════════════════╗
# ║  Gemini streaming adapter                                     ║
# ╚════════════════════════════════════════════════════════════════╝


async def _stream_gemini(
    model: str,
    messages: list[dict],
    max_output_tokens: int = 800,
    api_key: str = "",
    thinking_config: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Stream from Gemini ``streamGenerateContent`` endpoint.

    Args:
        model: Gemini model ID.
        messages: Conversation messages in generic format.
        max_output_tokens: Maximum output tokens.
        api_key: The Gemini API key to use (free or paid).
        thinking_config: Optional dict with ``thinkingBudget`` for
            Gemini thinking mode.  When set, adds
            ``generationConfig.thinkingConfig`` to the request.

    Yields dicts:
      ``{"type": "token", "text": "..."}``
      ``{"type": "usage", "input_tokens": N, "output_tokens": M, "thinking_tokens": K}``
      ``{"type": "error", ...}``  /  ``{"type": "rate_limited", ...}``
      ``{"type": "billing_error", ...}``
    """
    key = api_key or settings.gemini_api_key_free
    if not key:
        yield {"type": "error", "text": "GEMINI_API_KEY not configured"}
        return

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:streamGenerateContent"
    )

    # Convert generic messages → Gemini format
    contents: list[dict] = []
    system_instruction: Optional[dict] = None

    for msg in messages:
        if msg["role"] == "system":
            system_instruction = {"parts": [{"text": msg["content"]}]}
        elif msg["role"] == "user":
            contents.append(
                {"role": "user", "parts": [{"text": msg["content"]}]}
            )
        elif msg["role"] == "assistant":
            contents.append(
                {"role": "model", "parts": [{"text": msg["content"]}]}
            )

    gen_config: dict = {
        "maxOutputTokens": max_output_tokens,
        "temperature": 0.3,
    }

    # Inject thinking configuration when requested
    if thinking_config:
        gen_config["thinkingConfig"] = thinking_config

    payload: dict = {
        "contents": contents,
        "generationConfig": gen_config,
    }
    if system_instruction:
        payload["systemInstruction"] = system_instruction

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(90.0, connect=10.0)
    ) as client:
        async with client.stream(
            "POST",
            url,
            json=payload,
            params={"key": key, "alt": "sse"},
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status_code == 429:
                yield {"type": "rate_limited", "status": 429}
                return
            if resp.status_code == 403:
                body = await resp.aread()
                body_str = body.decode()[:300]
                # Check for billing/quota errors from paid key
                if "billing" in body_str.lower() or "quota" in body_str.lower():
                    yield {"type": "billing_error", "text": f"Gemini 403: {body_str}"}
                    return
                yield {"type": "error", "text": f"Gemini 403: {body_str}"}
                return
            if resp.status_code >= 400:
                body = await resp.aread()
                yield {
                    "type": "error",
                    "text": f"Gemini {resp.status_code}: "
                    f"{body.decode()[:200]}",
                }
                return

            thinking_tokens = 0
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    for cand in chunk.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            # Skip thought parts (thinking mode) — only yield answer text
                            if part.get("thought"):
                                continue
                            if "text" in part:
                                yield {"type": "token", "text": part["text"]}

                    usage = chunk.get("usageMetadata")
                    if usage:
                        # Gemini reports thoughtsTokenCount for thinking mode
                        t_tokens = usage.get("thoughtsTokenCount", 0)
                        if t_tokens:
                            thinking_tokens = t_tokens
                        yield {
                            "type": "usage",
                            "input_tokens": usage.get(
                                "promptTokenCount", 0
                            ),
                            "output_tokens": usage.get(
                                "candidatesTokenCount", 0
                            ),
                            "thinking_tokens": thinking_tokens,
                        }
                except json.JSONDecodeError:
                    continue


# ╔════════════════════════════════════════════════════════════════╗
# ║  Groq streaming adapter (OpenAI-compatible)                   ║
# ╚════════════════════════════════════════════════════════════════╝


async def _stream_groq(
    model: str,
    messages: list[dict],
    max_output_tokens: int = 800,
) -> AsyncGenerator[dict, None]:
    """
    Stream from Groq's OpenAI-compatible chat endpoint.

    Yields the same event dicts as ``_stream_gemini``.
    """
    if not settings.groq_api_key:
        yield {"type": "error", "text": "GROQ_API_KEY not configured"}
        return

    groq_model = model.removeprefix("groq:")
    url = "https://api.groq.com/openai/v1/chat/completions"

    payload = {
        "model": groq_model,
        "messages": messages,
        "max_tokens": max_output_tokens,
        "temperature": 0.3,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(90.0, connect=10.0)
    ) as client:
        async with client.stream(
            "POST",
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
        ) as resp:
            if resp.status_code == 429:
                yield {"type": "rate_limited", "status": 429}
                return
            if resp.status_code >= 400:
                body = await resp.aread()
                yield {
                    "type": "error",
                    "text": f"Groq {resp.status_code}: "
                    f"{body.decode()[:200]}",
                }
                return

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        if delta.get("content"):
                            yield {
                                "type": "token",
                                "text": delta["content"],
                            }

                    usage = chunk.get("usage")
                    if usage:
                        yield {
                            "type": "usage",
                            "input_tokens": usage.get("prompt_tokens", 0),
                            "output_tokens": usage.get(
                                "completion_tokens", 0
                            ),
                            "thinking_tokens": 0,
                        }
                except json.JSONDecodeError:
                    continue


# ╔════════════════════════════════════════════════════════════════╗
# ║  Public interface                                             ║
# ╚════════════════════════════════════════════════════════════════╝


async def generate_answer(
    model_id: str,
    chunks: list[RetrievalResult],
    question: str,
    history: list[dict] | None = None,
    max_output_tokens: int = 800,
    api_key: str = "",
    thinking_config: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Generate a streaming answer using the specified model.

    Args:
        model_id: The model to call.
        chunks: Retrieved context chunks.
        question: Student question.
        history: Conversation history.
        max_output_tokens: Max output tokens for this request.
        api_key: API key to use (router passes free or paid key).
        thinking_config: Thinking mode config for Gemini models.

    Yields dicts:
      ``{"type": "token", "text": "..."}``   — incremental text
      ``{"type": "usage", ...}``             — token counts (final chunk)
      ``{"type": "error", "text": "..."}``   — error
      ``{"type": "rate_limited", ...}``      — 429
      ``{"type": "billing_error", ...}``     — billing/quota error
    """
    messages = build_messages(question, chunks, history, model_id)
    provider = get_provider(model_id)

    if provider == "groq":
        async for event in _stream_groq(model_id, messages, max_output_tokens):
            yield event
    else:
        async for event in _stream_gemini(
            model_id, messages, max_output_tokens,
            api_key=api_key,
            thinking_config=thinking_config,
        ):
            yield event
