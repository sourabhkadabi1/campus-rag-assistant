"""
Application configuration — loaded entirely from environment variables.
Nothing is hardcoded: API keys, model names, limits, and prices all come
from .env or an admin settings table.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator
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


# ── Response profiles: (plan, detailed) -> {chunks, max_output, units} ──
RESPONSE_PROFILES: dict[tuple[str, bool], dict[str, int]] = {
    ("free", False):  {"chunks": 3, "max_output": 600,  "units": 1},
    ("free", True):   {"chunks": 5, "max_output": 1000, "units": 2},
    ("paid", False):  {"chunks": 4, "max_output": 800,  "units": 1},
    ("paid", True):   {"chunks": 6, "max_output": 2000, "units": 2},
}


# ── Detailed-detection keywords ──────────────────────────────────
DETAILED_KEYWORDS: list[str] = [
    "in detail", "step by step", "derive", "prove",
    "compare", "with example", "write code", "numerical",
]
DETAILED_WORD_THRESHOLD: int = 40  # >40 words = detailed


# ── Model pricing table ──────────────────────────────────────────

def _get_model_prices() -> dict[str, dict[str, float]]:
    """Per-model prices: input/output USD per 1M tokens. Free-key, Gemma and Groq cost 0."""
    # gemini-3.6-flash has promotional pricing until 2026-12-31
    flash_36_input = 0.75 if date.today() <= date(2026, 12, 31) else 1.50
    flash_36_output = 3.75 if date.today() <= date(2026, 12, 31) else 7.50
    return {
        "gemini-3.5-flash-lite":  {"input": 0.30, "output": 2.50},
        "gemini-3.1-flash-lite":  {"input": 0.25, "output": 1.50},
        "gemini-2.5-flash-lite":  {"input": 0.10, "output": 0.40},
        "gemini-3.6-flash":       {"input": flash_36_input, "output": flash_36_output},
        "gemini-3.8-flash":       {"input": 1.50, "output": 7.50},
        "gemma-4-26b":            {"input": 0.0, "output": 0.0},
        "gemma-4-31b":            {"input": 0.0, "output": 0.0},
        "groq:openai/gpt-oss-20b": {"input": 0.0, "output": 0.0},
    }

DEFAULT_MODEL_PRICES = _get_model_prices()


class Settings(BaseSettings):
    """All settings sourced from environment variables / .env file."""

    # ── API keys ──────────────────────────────────────────
    gemini_api_key: str      = Field(default="", alias="GEMINI_API_KEY")
    gemini_api_key_free: str = Field(default="", alias="GEMINI_API_KEY_FREE")
    gemini_api_key_paid: str = Field(default="", alias="GEMINI_API_KEY_PAID")
    groq_api_key: str        = Field(default="", alias="GROQ_API_KEY")

    @model_validator(mode="after")
    def _sync_gemini_keys(self) -> Settings:
        if self.gemini_api_key:
            if not self.gemini_api_key_free:
                self.gemini_api_key_free = self.gemini_api_key
            if not self.gemini_api_key_paid:
                self.gemini_api_key_paid = self.gemini_api_key
        elif self.gemini_api_key_free and not self.gemini_api_key_paid:
            self.gemini_api_key_paid = self.gemini_api_key_free
        elif self.gemini_api_key_paid and not self.gemini_api_key_free:
            self.gemini_api_key_free = self.gemini_api_key_paid
        return self

    # ── Supabase ──────────────────────────────────────────
    supabase_url: str        = Field(default="", alias="SUPABASE_URL")
    supabase_service_key: str = Field(default="", alias="SUPABASE_SERVICE_KEY")

    # ── Direct Postgres (asyncpg) ─────────────────────────
    database_url: str = Field(default="", alias="DATABASE_URL")

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = Field(default="", alias="REDIS_URL")

    # ── Model chains (comma-separated, priority order) ────
    model_chain: str | None = Field(default=None, alias="MODEL_CHAIN")
    model_chain_free: str = Field(
        default=(
            "gemini-3.5-flash-lite,gemini-3.1-flash-lite,"
            "gemini-2.5-flash-lite,gemma-4-26b,gemma-4-31b,"
            "groq:openai/gpt-oss-20b"
        ),
        alias="MODEL_CHAIN_FREE",
    )
    model_chain_paid: str = Field(
        default=(
            "gemini-3.5-flash-lite,gemini-3.1-flash-lite,"
            "gemini-2.5-flash-lite,gemma-4-26b,gemma-4-31b,"
            "groq:openai/gpt-oss-20b"
        ),
        alias="MODEL_CHAIN_PAID",
    )
    model_premium_thinking: str = Field(
        default="gemini-3.6-flash,gemini-3.8-flash",
        alias="MODEL_PREMIUM_THINKING",
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

    # ── Query pipeline ────────────────────────────────────
    cache_ttl_hours: int = Field(default=24, alias="CACHE_TTL_HOURS")

    # ── Thinking mode settings ────────────────────────────
    premium_enabled: bool = Field(default=False, alias="PREMIUM_ENABLED")
    thinking_daily_per_user: int = Field(default=1, alias="THINKING_DAILY_PER_USER")
    thinking_max_input_tokens: int = Field(default=8000, alias="THINKING_MAX_INPUT_TOKENS")
    thinking_budget_tokens: int = Field(default=2000, alias="THINKING_BUDGET_TOKENS")
    thinking_max_output_tokens: int = Field(default=4000, alias="THINKING_MAX_OUTPUT_TOKENS")

    # ── Cost tracking / balance guard ─────────────────────
    premium_daily_spend_cap_usd: float = Field(default=0.15, alias="PREMIUM_DAILY_SPEND_CAP_USD")
    premium_min_balance_usd: float = Field(default=2.0, alias="PREMIUM_MIN_BALANCE_USD")
    paid_min_balance_usd: float = Field(default=0.75, alias="PAID_MIN_BALANCE_USD")
    account_balance_usd: float = Field(default=5.0, alias="ACCOUNT_BALANCE_USD")

    # ── Router & limits ───────────────────────────────────
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

    # ── Quotas & payments ─────────────────────────────────
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

    # ── Backward compatibility aliases ───────────────────
    max_output_tokens: int = Field(default=800, alias="MAX_OUTPUT_TOKENS")
    max_output_tokens_detailed: int = Field(default=2000, alias="MAX_OUTPUT_TOKENS_DETAILED")
    retrieval_top_k: int = Field(default=4, alias="RETRIEVAL_TOP_K")
    retrieval_top_k_detailed: int = Field(default=6, alias="RETRIEVAL_TOP_K_DETAILED")
    paid_plan_price_paise: int = Field(default=9900, alias="PAID_PLAN_PRICE_PAISE")
    paid_plan_duration_days: int = Field(default=30, alias="PAID_PLAN_DURATION_DAYS")

    # ── Derived helpers ───────────────────────────────────

    @property
    def model_chain_list(self) -> list[str]:
        """Ordered list of models. If MODEL_CHAIN was explicitly set, uses that.
        Otherwise returns the full set of models across free, thinking, and paid chains."""
        if self.model_chain is not None:
            return [m.strip() for m in self.model_chain.split(",") if m.strip()]
        ordered = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.8-flash",
            "gemma-4-26b",
            "gemma-4-31b",
            "groq:openai/gpt-oss-20b",
        ]
        for m in self.model_chain_free_list + self.model_premium_thinking_list + self.model_chain_paid_list:
            if m not in ordered:
                ordered.append(m)
        return ordered

    @property
    def model_chain_free_list(self) -> list[str]:
        """Parse MODEL_CHAIN_FREE into an ordered list."""
        return [m.strip() for m in self.model_chain_free.split(",") if m.strip()]

    @property
    def model_chain_paid_list(self) -> list[str]:
        """Parse MODEL_CHAIN_PAID into an ordered list."""
        return [m.strip() for m in self.model_chain_paid.split(",") if m.strip()]

    @property
    def model_premium_thinking_list(self) -> list[str]:
        """Parse MODEL_PREMIUM_THINKING into an ordered list."""
        return [m.strip() for m in self.model_premium_thinking.split(",") if m.strip()]

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
