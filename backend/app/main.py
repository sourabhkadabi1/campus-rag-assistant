"""
FastAPI application — entry point.
Phase 6: Sentry error tracking, structured logging, request-ID middleware,
         comprehensive /health endpoint.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, close_db, get_pool
from app.middleware import RequestIdMiddleware, setup_logging
from app.services.embeddings import load_model as load_embedding_model
from app.services.model_verifier import verify_configured_models
from app.services.rate_counter import init_rate_store
from app.routers import admin as admin_router
from app.routers import ask as ask_router
from app.routers import chat as chat_router
from app.routers import models as models_router
from app.routers import quota as quota_router
from app.routers import plans as plans_router
from app.routers import payments as payments_router
from app.routers import practice as practice_router

# ── Logging setup (JSON in production, plain text in dev) ─────────
setup_logging(
    json_format=(settings.log_format.lower() == "json"),
    level=settings.log_level,
)
logger = logging.getLogger(__name__)

# ── Sentry error tracking (optional) ──────────────────────────────
if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
        logger.info("Sentry initialised (env=%s)", settings.environment)
    except ImportError:
        logger.warning("sentry-sdk not installed — error tracking disabled")

# Track startup time for /health uptime
_startup_time: float = time.time()
_embedding_ready: bool = False


# ── Lifespan (startup / shutdown) ─────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources on startup; tear down on shutdown."""
    global _embedding_ready
    logger.info("Starting up … (env=%s)", settings.environment)

    # 1. Database pool
    try:
        await init_db()
        logger.info("Database pool ready")
    except Exception as exc:
        logger.warning("Could not connect to database: %s", exc)
        logger.warning("Running without database — only useful for local dev")

    # 2. Embedding model (blocks until weights are downloaded/loaded)
    try:
        load_embedding_model()
        _embedding_ready = True
    except Exception as exc:
        logger.warning("Could not load embedding model: %s", exc)

    # 3. Rate counter store (Redis or in-memory fallback)
    try:
        await init_rate_store()
    except Exception as exc:
        logger.warning("Could not initialise rate store: %s", exc)

    # 4. Model ID verification (Phase 3, step 0)
    try:
        registry = await verify_configured_models()
        verified = sum(1 for s in registry.values() if s.is_verified)
        total = len(registry)
        logger.info("Model verification complete: %d/%d models verified", verified, total)
        for mid, status in registry.items():
            if not status.is_verified:
                logger.warning("  ✗ %s — %s", mid, status.error_message or "not found")
    except Exception as exc:
        logger.warning("Model verification failed (will use full chain): %s", exc)

    yield  # ── app is running ──

    logger.info("Shutting down …")
    await close_db()


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="College RAG Assistant",
    version="0.7.0",
    description="Phase 1–7: Ingestion + Query + Router + Quotas/Plans/Payments + Security/Hardening + Practice/Quiz Generator",
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────

# Request-ID and access logging (Phase 6)
app.add_middleware(RequestIdMiddleware)

# CORS — allow localhost in dev and Vercel in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|.*\.vercel\.app)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────

app.include_router(admin_router.router)
app.include_router(admin_router.auth_router)
app.include_router(ask_router.router)
app.include_router(chat_router.router)
app.include_router(models_router.router)
app.include_router(quota_router.router)
app.include_router(plans_router.router)
app.include_router(payments_router.router)
app.include_router(practice_router.router)


# ── Root ──────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return {
        "message": "College RAG Assistant Backend is running",
        "version": "0.7.0",
        "docs": "/docs",
        "health": "/health",
    }


# ── Health check (Phase 6: deep probe) ───────────────────────────


@app.get("/health")
async def health():
    """
    Deep health check — probes DB, Redis, and embedding model.

    Returns HTTP 200 when healthy, HTTP 503 when any critical
    dependency is unavailable.
    """
    checks: dict[str, str] = {}
    healthy = True

    # 1. Database probe
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        healthy = False

    # 2. Embedding model
    checks["embedding_model"] = "ok" if _embedding_ready else "not_loaded"
    if not _embedding_ready:
        healthy = False

    # 3. Redis / rate-counter store
    try:
        from app.services.rate_counter import _store  # type: ignore[attr-defined]
        if _store is not None:
            checks["redis"] = "ok"
        else:
            checks["redis"] = "in_memory_fallback"
    except Exception:
        checks["redis"] = "unknown"

    uptime_seconds = int(time.time() - _startup_time)
    status_code = 200 if healthy else 503
    body = {
        "status": "ok" if healthy else "degraded",
        "version": "0.6.0",
        "environment": settings.environment,
        "uptime_seconds": uptime_seconds,
        "checks": checks,
    }

    from fastapi.responses import JSONResponse
    return JSONResponse(content=body, status_code=status_code)
