"""
Tests for configuration loading.
Verifies Settings parses MODEL_CHAIN correctly and that
DEFAULT_MODEL_LIMITS contains all expected models.
"""

from __future__ import annotations

from app.config import DEFAULT_MODEL_LIMITS, Settings


class TestSettings:
    def test_model_chain_parsing(self):
        """MODEL_CHAIN string is split into a list."""
        s = Settings(MODEL_CHAIN="model-a,model-b, model-c")
        assert s.model_chain_list == ["model-a", "model-b", "model-c"]

    def test_model_chain_default(self):
        s = Settings()
        chain = s.model_chain_list
        assert len(chain) == 8
        assert chain[0] == "gemini-3.5-flash-lite"
        assert chain[-1] == "groq:openai/gpt-oss-20b"

    def test_empty_chain(self):
        s = Settings(MODEL_CHAIN="")
        assert s.model_chain_list == []

    def test_max_upload_bytes(self):
        s = Settings(MAX_UPLOAD_SIZE_MB=10)
        assert s.max_upload_bytes == 10 * 1024 * 1024

    def test_summary_reserve_default(self):
        s = Settings()
        assert s.summary_reserve_rpd == 10


class TestDefaultModelLimits:
    def test_all_chain_models_have_limits(self):
        """Every model in the default chain has seed limits."""
        s = Settings()
        for model in s.model_chain_list:
            assert model in DEFAULT_MODEL_LIMITS, (
                f"Model {model} missing from DEFAULT_MODEL_LIMITS"
            )

    def test_limits_have_required_keys(self):
        for model, limits in DEFAULT_MODEL_LIMITS.items():
            assert "rpm" in limits, f"{model} missing rpm"
            assert "tpm" in limits, f"{model} missing tpm"
            assert "rpd" in limits, f"{model} missing rpd"
            assert all(v > 0 for v in limits.values()), (
                f"{model} has zero/negative limit"
            )

    def test_summary_models_in_limits(self):
        s = Settings()
        assert s.summary_model in DEFAULT_MODEL_LIMITS
        assert s.summary_fallback in DEFAULT_MODEL_LIMITS
