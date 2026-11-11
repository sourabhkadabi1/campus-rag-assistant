"""
Chapter summary generation via LLM.

Uses SUMMARY_MODEL (fallback: SUMMARY_FALLBACK) through the Gemini REST API.
Respects daily RPD limits and SUMMARY_RESERVE_RPD.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from typing import Optional

import httpx

from app.config import DEFAULT_MODEL_LIMITS, settings
from app.database import execute, fetchrow

logger = logging.getLogger(__name__)

# ── In-memory daily usage counter ─────────────────────────────────
# In production, these would live in Redis for cross-process safety.
_daily_counts: dict[str, dict[str, int]] = {}     # {date: {model: count}}


def _today() -> str:
    return date.today().isoformat()


def _get_count(model: str) -> int:
    today = _today()
    return _daily_counts.get(today, {}).get(model, 0)


def _increment(model: str) -> None:
    today = _today()
    if today not in _daily_counts:
        _daily_counts.clear()
        _daily_counts[today] = {}
    _daily_counts[today][model] = _daily_counts[today].get(model, 0) + 1


def _can_use(model: str) -> bool:
    """True if *model* has remaining RPD capacity for summaries."""
    rpd = DEFAULT_MODEL_LIMITS.get(model, {}).get("rpd", 0)
    return rpd > 0 and _get_count(model) < rpd


# ── Gemini API caller ─────────────────────────────────────────────


async def _call_gemini(model: str, prompt: str) -> Optional[str]:
    """Single Gemini generateContent call. Returns text or None."""
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — skipping summary")
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.3},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            params={"key": settings.gemini_api_key},
        )

    if resp.status_code == 429:
        logger.warning("429 rate-limited on %s for summary", model)
        return None
    if resp.status_code != 200:
        logger.error("Gemini %s error %d: %s", model, resp.status_code, resp.text[:300])
        return None

    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected Gemini response shape: %s", exc)
        return None


# ── Summary prompt & generation ───────────────────────────────────


_SUMMARY_PROMPT = """\
Summarise the following chapter for a college student preparing for exams.

Chapter {ch_no}: {ch_title}

Instructions:
- Clear, structured summary covering all major topics.
- 5–10 key concepts with one-line explanations.
- Include important formulas / definitions if present.
- 300–500 words, bullet points for readability.

Format:
## Summary
[summary]

## Key Concepts
- [concept]: [explanation]
…

--- Chapter text ---
{text}
"""


async def _generate_one(
    chapter_no: int, title: str, text: str
) -> tuple[Optional[str], Optional[str]]:
    """Try SUMMARY_MODEL, then SUMMARY_FALLBACK. Returns (text, model)."""
    prompt = _SUMMARY_PROMPT.format(
        ch_no=chapter_no,
        ch_title=title or "Untitled",
        text=text[:8000],           # keep within token budget
    )

    for model in (settings.summary_model, settings.summary_fallback):
        if not _can_use(model):
            logger.info("Model %s at RPD limit for summaries", model)
            continue
        result = await _call_gemini(model, prompt)
        if result:
            _increment(model)
            return result, model
        logger.warning("Model %s failed for summary — trying next", model)

    return None, None


def _parse_key_concepts(text: str) -> list[str]:
    """Pull bullet items from the 'Key Concepts' section."""
    concepts: list[str] = []
    in_section = False
    for line in text.split("\n"):
        stripped = line.strip()
        if "key concept" in stripped.lower() or stripped.startswith("## Key"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## "):
                break
            if stripped.startswith("- "):
                concepts.append(stripped[2:].strip())
    return concepts


# ── Public entry point ────────────────────────────────────────────


async def generate_chapter_summaries(
    document_id: str,
    chapter_data: list[dict],
) -> None:
    """
    Generate and store summaries for each chapter.

    *chapter_data*: list of ``{"chapter_no": int, "title": str, "text": str}``
    """
    logger.info("Generating summaries for %d chapters (doc %s)",
                len(chapter_data), document_id)

    for ch in chapter_data:
        ch_no = ch["chapter_no"]

        # Skip if summary already exists (re-upload)
        existing = await fetchrow(
            "SELECT id FROM chapter_summaries WHERE document_id=$1 AND chapter_no=$2",
            document_id, ch_no,
        )
        if existing:
            logger.info("Summary already exists for ch %d — skipping", ch_no)
            continue

        summary_text, model_used = await _generate_one(
            ch_no, ch["title"], ch["text"]
        )

        if summary_text and model_used:
            concepts = _parse_key_concepts(summary_text)
            await execute(
                """INSERT INTO chapter_summaries
                   (id, document_id, chapter_no, chapter_title,
                    summary, key_concepts, model_used)
                   VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7)
                   ON CONFLICT (document_id, chapter_no) DO UPDATE
                   SET summary=$5, key_concepts=$6::jsonb,
                       model_used=$7, generated_at=NOW()""",
                str(uuid.uuid4()), document_id, ch_no,
                ch["title"], summary_text,
                json.dumps(concepts), model_used,
            )
            logger.info("Saved summary for ch %d (model=%s)", ch_no, model_used)
        else:
            logger.warning("Could not generate summary for ch %d — models exhausted", ch_no)
