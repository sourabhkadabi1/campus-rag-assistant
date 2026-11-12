"""
FastAPI application — entry point.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, close_db
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources on startup; tear down on shutdown."""
    logger.info("Starting up …")

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
    except Exception as exc:
        logger.warning("Could not load embedding model: %s", exc)

    # 3. Rate counter store (Redis or in-memory fallback)
    try:
        await init_rate_store()
    except Exception as exc:
        logger.warning("Could not initialise rate store: %s", exc)

    # 4. Model ID verification (Phase 3, step 0)
    #    Fetches available models from Gemini/Groq APIs, verifies
    #    MODEL_CHAIN entries, and excludes invalid IDs.
    try:
        registry = await verify_configured_models()
        verified = sum(1 for s in registry.values() if s.is_verified)
        total = len(registry)
        logger.info(
            "Model verification complete: %d/%d models verified", verified, total
        )
        for mid, status in registry.items():
            if not status.is_verified:
                logger.warning(
                    "  ✗ %s — %s", mid, status.error_message or "not found"
                )
    except Exception as exc:
        logger.warning("Model verification failed (will use full chain): %s", exc)

    yield  # ── app is running ──

    logger.info("Shutting down …")
    await close_db()


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="College RAG Assistant",
    version="0.4.0",
    description="Phase 1+2+3+4 — Ingestion + Query + Router + Quotas/Plans/Payments",
    lifespan=lifespan,
)

# CORS — permissive for dev; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────

app.include_router(admin_router.router)
app.include_router(ask_router.router)
app.include_router(chat_router.router)
app.include_router(models_router.router)
app.include_router(quota_router.router)
app.include_router(plans_router.router)
app.include_router(payments_router.router)


# ── Health check ──────────────────────────────────────────────────


@app.get("/")
async def root():
    return {
        "message": "College RAG Assistant Backend is running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
