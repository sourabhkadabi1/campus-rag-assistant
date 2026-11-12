"""
Admin model status router — model verification, runtime status, and management.

Phase 3 admin endpoints for inspecting and controlling LLM model state:
- View combined verification + runtime status for all configured models.
- Toggle models enabled/disabled.
- Clear cooldowns after 429/5xx recovery.
- Re-run model verification against provider APIs.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services import model_verifier, rate_counter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/models", tags=["admin-models"])


# ── Pydantic request / response models ───────────────────────────


class ModelStatusResponse(BaseModel):
    """Combined verification + runtime status for a single model."""

    # Identification
    model_id: str
    provider: str

    # Verification fields
    is_verified: bool
    closest_match: Optional[str] = None
    error_message: Optional[str] = None
    verified_at: Optional[str] = None

    # Runtime fields
    is_enabled: bool
    is_available: bool
    status_reason: str
    cooldown_remaining_seconds: float
    rpm_used: int
    rpm_limit: int
    tpm_used: int
    tpm_limit: int
    rpd_used: int
    rpd_limit: int
    tokens_today: int
    is_summary_model: bool
    reserve_rpd: int
    reset_timezone: str


class ToggleRequest(BaseModel):
    """Optional body for the toggle endpoint."""

    enabled: Optional[bool] = None


class ToggleResponse(BaseModel):
    """Response after toggling a model's enabled state."""

    model_id: str
    is_enabled: bool


class ClearCooldownResponse(BaseModel):
    """Response after clearing a model's cooldown."""

    model_id: str
    cooldown_cleared: bool


class VerificationStatusResponse(BaseModel):
    """Verification result for a single model (returned from re-verify)."""

    model_id: str
    provider: str
    is_verified: bool
    is_enabled: bool
    closest_match: Optional[str] = None
    error_message: Optional[str] = None
    verified_at: Optional[str] = None


# ── GET /admin/models/status ─────────────────────────────────────


@router.get("/status", response_model=list[ModelStatusResponse])
async def get_all_model_status() -> list[ModelStatusResponse]:
    """
    Return combined verification and runtime status for every configured model.

    Merges data from the model verification registry (provider, verified status,
    closest match, error) with live rate-counter metrics (RPM/TPM/RPD usage,
    cooldown, enabled state, availability).
    """
    registry = model_verifier.get_model_registry()

    # Collect all configured model IDs (chain + summary models)
    configured: list[str] = []
    for m in settings.model_chain_list:
        if m not in configured:
            configured.append(m)
    for m in (settings.summary_model, settings.summary_fallback):
        if m and m not in configured:
            configured.append(m)

    results: list[ModelStatusResponse] = []

    for model_id in configured:
        # Runtime status from rate counter
        runtime = await rate_counter.get_model_full_status(model_id)

        # Verification status from registry
        verif = registry.get(model_id)

        results.append(
            ModelStatusResponse(
                model_id=model_id,
                provider=verif.provider if verif else model_verifier.get_provider(model_id),
                is_verified=verif.is_verified if verif else False,
                closest_match=verif.closest_match if verif else None,
                error_message=verif.error_message if verif else None,
                verified_at=(
                    verif.verified_at.isoformat() if verif and verif.verified_at else None
                ),
                is_enabled=runtime["is_enabled"],
                is_available=runtime["is_available"],
                status_reason=runtime["status_reason"],
                cooldown_remaining_seconds=runtime["cooldown_remaining_seconds"],
                rpm_used=runtime["rpm_used"],
                rpm_limit=runtime["rpm_limit"],
                tpm_used=runtime["tpm_used"],
                tpm_limit=runtime["tpm_limit"],
                rpd_used=runtime["rpd_used"],
                rpd_limit=runtime["rpd_limit"],
                tokens_today=runtime["tokens_today"],
                is_summary_model=runtime["is_summary_model"],
                reserve_rpd=runtime["reserve_rpd"],
                reset_timezone=runtime["reset_timezone"],
            )
        )

    logger.debug("Returned status for %d configured models", len(results))
    return results


# ── POST /admin/models/{model_id}/toggle ─────────────────────────


@router.post("/{model_id:path}/toggle", response_model=ToggleResponse)
async def toggle_model(model_id: str, body: ToggleRequest | None = None) -> ToggleResponse:
    """
    Toggle a model's enabled/disabled status.

    If ``body.enabled`` is provided, the model is set to that state explicitly.
    If omitted (or body is null), the current state is flipped.
    """
    # Validate that the model_id is one we know about
    registry = model_verifier.get_model_registry()
    all_configured = set(settings.model_chain_list)
    if settings.summary_model:
        all_configured.add(settings.summary_model)
    if settings.summary_fallback:
        all_configured.add(settings.summary_fallback)

    if model_id not in all_configured and model_id not in registry:
        raise HTTPException(404, f"Model '{model_id}' is not configured")

    enabled_flag = body.enabled if body else None
    new_state = await rate_counter.toggle_model_enabled(model_id, enabled_flag)

    action = "enabled" if new_state else "disabled"
    logger.info("Model %s %s by admin", model_id, action)

    return ToggleResponse(model_id=model_id, is_enabled=new_state)


# ── POST /admin/models/{model_id}/clear-cooldown ─────────────────


@router.post("/{model_id:path}/clear-cooldown", response_model=ClearCooldownResponse)
async def clear_model_cooldown(model_id: str) -> ClearCooldownResponse:
    """
    Clear a model's cooldown timer.

    Useful when a model has recovered from a 429 or 5xx error and should be
    made available immediately rather than waiting for the cooldown to expire.
    """
    # Validate that the model_id is one we know about
    registry = model_verifier.get_model_registry()
    all_configured = set(settings.model_chain_list)
    if settings.summary_model:
        all_configured.add(settings.summary_model)
    if settings.summary_fallback:
        all_configured.add(settings.summary_fallback)

    if model_id not in all_configured and model_id not in registry:
        raise HTTPException(404, f"Model '{model_id}' is not configured")

    store = rate_counter.get_rate_store()
    await store.clear_cooldown(model_id)

    logger.info("Cooldown cleared for model %s by admin", model_id)
    return ClearCooldownResponse(model_id=model_id, cooldown_cleared=True)


# ── POST /admin/models/reverify ──────────────────────────────────


@router.post("/reverify", response_model=list[VerificationStatusResponse])
async def reverify_models() -> list[VerificationStatusResponse]:
    """
    Re-run model verification against provider APIs.

    Fetches fresh model lists from Gemini and Groq, then re-verifies every
    configured model. Returns the updated verification registry.
    """
    logger.info("Admin triggered model re-verification")
    registry = await model_verifier.verify_configured_models()

    results: list[VerificationStatusResponse] = []
    for status in registry.values():
        results.append(
            VerificationStatusResponse(
                model_id=status.model_id,
                provider=status.provider,
                is_verified=status.is_verified,
                is_enabled=status.is_enabled,
                closest_match=status.closest_match,
                error_message=status.error_message,
                verified_at=status.verified_at.isoformat() if status.verified_at else None,
            )
        )

    logger.info("Re-verification complete: %d models checked", len(results))
    return results
