"""
Model verification service — verifies model IDs against provider APIs.

At backend startup:
- Fetches available model IDs from Gemini and Groq APIs.
- Compares MODEL_CHAIN_FREE, MODEL_CHAIN_PAID, MODEL_PREMIUM_THINKING,
  SUMMARY_MODEL, and SUMMARY_FALLBACK against the lists.
- Uses GEMINI_API_KEY_FREE for free chain models and GEMINI_API_KEY_PAID
  for paid/thinking chain models.
- For missing IDs: logs a clear error, suggests the closest match, and excludes
  the model from the active chain so it is never called.
- Maintains in-memory registry of verification statuses for admin inspection.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelVerificationStatus:
    """Status record for a single model ID."""
    model_id: str
    provider: str
    is_verified: bool
    is_enabled: bool = True
    closest_match: Optional[str] = None
    error_message: Optional[str] = None
    verified_at: Optional[datetime] = None


# Global registry of model statuses: model_id -> ModelVerificationStatus
_MODEL_REGISTRY: dict[str, ModelVerificationStatus] = {}

# Cached lists of available IDs from providers
_CACHED_GEMINI_MODELS: list[str] = []
_CACHED_GROQ_MODELS: list[str] = []


def get_provider(model_id: str) -> str:
    """Return provider identifier ('groq' or 'gemini')."""
    return "groq" if model_id.startswith("groq:") else "gemini"


def clean_model_id(model_id: str) -> str:
    """Return bare model ID without provider prefix."""
    return model_id.removeprefix("groq:").strip()


async def fetch_gemini_model_ids(api_key: Optional[str] = None) -> list[str]:
    """Fetch model IDs from Gemini list models endpoint."""
    key = api_key or settings.gemini_api_key_free
    if not key:
        logger.warning("[ModelVerifier] GEMINI_API_KEY not configured — skipping Gemini discovery")
        return []

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params={"key": key})
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            ids = sorted(m.get("name", "").removeprefix("models/") for m in models if m.get("name"))
            return ids
    except Exception as exc:
        logger.error("[ModelVerifier] Failed to fetch Gemini models: %s", exc)
        return []


async def fetch_groq_model_ids(api_key: Optional[str] = None) -> list[str]:
    """Fetch model IDs from Groq list models endpoint."""
    key = api_key or settings.groq_api_key
    if not key:
        logger.warning("[ModelVerifier] GROQ_API_KEY not configured — skipping Groq discovery")
        return []

    url = "https://api.groq.com/openai/v1/models"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            ids = sorted(m.get("id", "") for m in models if m.get("id"))
            return ids
    except Exception as exc:
        logger.error("[ModelVerifier] Failed to fetch Groq models: %s", exc)
        return []


def find_closest_match(target: str, candidates: list[str]) -> Optional[str]:
    """Find the most plausible match from candidate model IDs."""
    if not candidates:
        return None

    # 1. Exact case-insensitive match
    for cand in candidates:
        if target.lower() == cand.lower():
            return cand

    # 2. Substring / prefix matches
    substring_matches = [c for c in candidates if target.lower() in c.lower() or c.lower() in target.lower()]
    if substring_matches:
        return substring_matches[0]

    # 3. Fuzzy matching using difflib
    close = difflib.get_close_matches(target, candidates, n=1, cutoff=0.35)
    return close[0] if close else None


async def verify_configured_models(
    gemini_ids: Optional[list[str]] = None,
    groq_ids: Optional[list[str]] = None,
) -> dict[str, ModelVerificationStatus]:
    """
    Verify all models configured in MODEL_CHAIN_FREE, MODEL_CHAIN_PAID,
    MODEL_PREMIUM_THINKING, SUMMARY_MODEL, and SUMMARY_FALLBACK.

    Uses GEMINI_API_KEY_FREE for free chain Gemini models and
    GEMINI_API_KEY_PAID for paid/thinking chain Gemini models.
    Excludes unverified models from active routing so they are never called.
    """
    global _CACHED_GEMINI_MODELS, _CACHED_GROQ_MODELS, _MODEL_REGISTRY

    # Fetch model lists using both keys if available
    if gemini_ids is None:
        # Try both keys — merge the results
        free_ids = await fetch_gemini_model_ids(settings.gemini_api_key_free)
        paid_ids = await fetch_gemini_model_ids(settings.gemini_api_key_paid)
        gemini_ids = sorted(set(free_ids) | set(paid_ids))
    if groq_ids is None:
        groq_ids = await fetch_groq_model_ids()

    _CACHED_GEMINI_MODELS = gemini_ids
    _CACHED_GROQ_MODELS = groq_ids

    # Collect all configured model names to check, grouped by chain
    configured_models: list[str] = []
    for m in settings.model_chain_free_list:
        if m not in configured_models:
            configured_models.append(m)
    for m in settings.model_chain_paid_list:
        if m not in configured_models:
            configured_models.append(m)
    for m in settings.model_premium_thinking_list:
        if m not in configured_models:
            configured_models.append(m)

    for m in (settings.summary_model, settings.summary_fallback):
        if m and m not in configured_models:
            configured_models.append(m)

    results: dict[str, ModelVerificationStatus] = {}
    now = datetime.now(timezone.utc)

    gemini_available = bool(gemini_ids)
    groq_available = bool(groq_ids)

    for model_id in configured_models:
        provider = get_provider(model_id)
        bare_id = clean_model_id(model_id)

        if provider == "groq":
            candidates = groq_ids
            has_api = groq_available
        else:
            candidates = gemini_ids
            has_api = gemini_available

        is_found = bare_id in candidates

        if is_found:
            status = ModelVerificationStatus(
                model_id=model_id,
                provider=provider,
                is_verified=True,
                verified_at=now,
            )
            logger.info("✓ Model verified: %s (%s)", model_id, provider)
        elif has_api:
            suggestion = find_closest_match(bare_id, candidates)
            sugg_str = f"groq:{suggestion}" if (provider == "groq" and suggestion) else suggestion
            error_msg = f"Model '{model_id}' not found in {provider} model list."
            if suggestion:
                error_msg += f" Closest match: '{sugg_str}'."
            logger.error(
                "✗ [ModelVerifier] %s Excluded from active chain.",
                error_msg,
            )
            status = ModelVerificationStatus(
                model_id=model_id,
                provider=provider,
                is_verified=False,
                closest_match=sugg_str,
                error_message=error_msg,
                verified_at=now,
            )
        else:
            error_msg = f"{provider.upper()} API unreachable or key not set; cannot verify '{model_id}'."
            logger.warning("[ModelVerifier] %s", error_msg)
            status = ModelVerificationStatus(
                model_id=model_id,
                provider=provider,
                is_verified=False,
                error_message=error_msg,
                verified_at=now,
            )

        results[model_id] = status

    _MODEL_REGISTRY.update(results)
    return results


def get_model_registry() -> dict[str, ModelVerificationStatus]:
    """Return the current model verification registry."""
    return dict(_MODEL_REGISTRY)


def is_model_verified(model_id: str) -> bool:
    """Check if a model ID has been verified."""
    entry = _MODEL_REGISTRY.get(model_id)
    return entry.is_verified if entry else False


def get_verified_chain(chain_type: str = "free") -> list[str]:
    """
    Get the configured chain filtered to only verified models.

    Args:
        chain_type: 'free', 'paid', or 'thinking'.

    If no models are verified (e.g. offline dev/testing), returns the original chain
    so testing with mock responses can still operate.
    """
    if chain_type == "paid":
        configured = settings.model_chain_paid_list
    elif chain_type == "thinking":
        configured = settings.model_premium_thinking_list
    else:
        configured = settings.model_chain_free_list

    verified = [m for m in configured if is_model_verified(m)]
    if not verified and not _CACHED_GEMINI_MODELS and not _CACHED_GROQ_MODELS:
        # No verification was possible (e.g. no internet/keys in local test)
        return configured
    return verified


# Keep backward-compatible alias for imports that use the old name
def get_verified_active_chain() -> list[str]:
    """Backward-compatible alias — returns the free chain."""
    return get_verified_chain("free")
