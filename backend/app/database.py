"""
Async database helpers built on asyncpg.
Provides a connection-pool singleton and thin wrappers for common queries.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_db() -> asyncpg.Pool:
    """Create (or return existing) asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    dsn = settings.database_url
    if not dsn:
        raise ValueError(
            "DATABASE_URL is not set.  Add it to .env — see .env.example."
        )

    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )

    # Ensure pgvector extension is available
    async with _pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    logger.info("Database connection pool initialised")
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Return the pool, lazily initialising if needed."""
    if _pool is None:
        return await init_db()
    return _pool


async def close_db() -> None:
    """Gracefully close the pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


# ── Convenience wrappers ──────────────────────────────────────────


async def execute(query: str, *args: Any) -> str:
    """Execute a statement and return its status string."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    """Return all matching rows."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> Optional[asyncpg.Record]:
    """Return the first matching row, or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args: Any) -> Any:
    """Return a single scalar value."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)
