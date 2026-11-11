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
from app.routers import admin as admin_router

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

    yield  # ── app is running ──

    logger.info("Shutting down …")
    await close_db()


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="College RAG Assistant",
    version="0.1.0",
    description="Phase 1 — Document ingestion and admin API",
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


# ── Health check ──────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}
