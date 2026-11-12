"""
Application configuration — loaded entirely from environment variables.
Nothing is hardcoded: API keys, model names, limits, and prices all come
from .env or an admin settings table.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


# ── Seed model limits (editable at runtime via admin) ─────────────
# Values come from the PROJECT.md table.  They are defaults only;
# the admin UI / settings table can override them without code changes.
DEFAULT_MODEL_LIMITS: dict[str, dict[str, int]] = {
    "gemini-3.5-flash-lite":  {"rpm": 15, "tpm": 250_000, "rpd": 500},
    "gemini-3.1-flash-lite":  {"rpm": 15, "tpm": 250_000, "rpd": 500},
    "gemini-2.5-flash-lite":  {"rpm": 10, "tpm": 250_000, "rpd": 20},
    "gemini-3.6-flash":       {"rpm": 5,  "tpm": 250_000, "rpd": 20},
    "gemini-3.8-flash":       {"rpm": 5,  "tpm": 250_000, "rpd": 20},
    "gemma-4-26b":            {"rpm": 30, "tpm": 16_000,  "rpd": 14_400},
    "gemma-4-31b":            {"rpm": 30, "tpm": 16_000,  "rpd": 14_400},
    "groq:openai/gpt-oss-20b": {"rpm": 30, "tpm": 8_000, "rpd": 1_000},
}


class Settings(BaseSettings):
    """All settings sourced from environment variables / .env file."""

    # ── API keys ──────────────────────────────────────────
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    groq_api_key: str   = Field(default="", alias="GROQ_API_KEY")

    # ── Supabase ──────────────────────────────────────────
    supabase_url: str        = Field(default="", alias="SUPABASE_URL")
    supabase_service_key: str = Field(default="", alias="SUPABASE_SERVICE_KEY")

    # ── Direct Postgres (asyncpg) ─────────────────────────
    database_url: str = Field(default="", alias="DATABASE_URL")

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = Field(default="", alias="REDIS_URL")

    # ── Model chain (comma-separated, priority order) ─────
    model_chain: str = Field(
        default=(
            "gemini-3.5-flash-lite,gemini-3.1-flash-lite,"
            "gemini-2.5-flash-lite,gemini-3.6-flash,"
            "gemini-3.8-flash,gemma-4-26b,gemma-4-31b,"
            "groq:openai/gpt-oss-20b"
        ),
        alias="MODEL_CHAIN",
    )

    # ── Summary generation ────────────────────────────────
    summary_model: str     = Field(default="gemini-3.6-flash", alias="SUMMARY_MODEL")
    summary_fallback: str  = Field(default="gemini-3.8-flash", alias="SUMMARY_FALLBACK")
    summary_reserve_rpd: int = Field(default=10, alias="SUMMARY_RESERVE_RPD")

    # ── Embedding model (local sentence-transformers) ─────
    embedding_model_name: str = Field(
        default="BAAI/bge-small-en-v1.5", alias="EMBEDDING_MODEL"
    )

    # ── Upload ────────────────────────────────────────────
    upload_dir: str       = Field(default="uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=50, alias="MAX_UPLOAD_SIZE_MB")

    # ── Chunking ──────────────────────────────────────────
    chunk_size_tokens: int    = Field(default=700, alias="CHUNK_SIZE_TOKENS")
    chunk_overlap_tokens: int = Field(default=100, alias="CHUNK_OVERLAP_TOKENS")

    # ── Query pipeline (Phase 2) ─────────────────────────
    cache_ttl_hours: int = Field(default=24, alias="CACHE_TTL_HOURS")
    max_output_tokens: int = Field(default=800, alias="MAX_OUTPUT_TOKENS")
    max_output_tokens_detailed: int = Field(
        default=2000, alias="MAX_OUTPUT_TOKENS_DETAILED"
    )
    retrieval_top_k: int = Field(default=4, alias="RETRIEVAL_TOP_K")
    retrieval_top_k_detailed: int = Field(
        default=6, alias="RETRIEVAL_TOP_K_DETAILED"
    )

    # ── Router & limits (Phase 3) ────────────────────────
    provider_reset_timezone: str = Field(
        default="UTC", alias="PROVIDER_RESET_TIMEZONE"
    )
    router_queue_timeout_seconds: int = Field(
        default=60, alias="ROUTER_QUEUE_TIMEOUT_SECONDS"
    )
    router_cooldown_429_seconds: int = Field(
        default=60, alias="ROUTER_COOLDOWN_429_SECONDS"
    )
    router_cooldown_5xx_seconds: int = Field(
        default=15, alias="ROUTER_COOLDOWN_5XX_SECONDS"
    )
    router_rpd_threshold_pct: float = Field(
        default=0.95, alias="ROUTER_RPD_THRESHOLD_PCT"
    )

    # ── Quotas & payments (Phase 4) ──────────────────────
    razorpay_key_id: str = Field(default="", alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(default="", alias="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: str = Field(default="", alias="RAZORPAY_WEBHOOK_SECRET")
    budget_guard_threshold: float = Field(
        default=0.90, alias="BUDGET_GUARD_THRESHOLD",
        description="When combined free-provider capacity exceeds this %, FREE users switch to retrieval-only.",
    )
    monthly_spend_cap_usd: float = Field(
        default=0.0, alias="MONTHLY_SPEND_CAP_USD",
        description="Hard monthly spend cap for paid API usage. 0 = disabled.",
    )
    user_rpm_limit: int = Field(
        default=5, alias="USER_RPM_LIMIT",
        description="Max requests per minute per user (abuse protection).",
    )
    paid_plan_price_paise: int = Field(
        default=9900, alias="PAID_PLAN_PRICE_PAISE",
        description="Razorpay order amount in paise (9900 = ₹99).",
    )
    paid_plan_duration_days: int = Field(
        default=30, alias="PAID_PLAN_DURATION_DAYS",
    )

    # ── Derived helpers ───────────────────────────────────

    @property
    def model_chain_list(self) -> list[str]:
        """Parse MODEL_CHAIN into an ordered list."""
        return [m.strip() for m in self.model_chain.split(",") if m.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    model_config = {
        "env_file": (".env", "../.env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


# Singleton — import this everywhere
settings = Settings()
