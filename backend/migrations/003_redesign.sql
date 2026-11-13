-- ============================================================
-- Redesign: dual chains, thinking mode, cost tracking
-- Run AFTER 002_phase4.sql
-- ADDITIVE ONLY — no data deleted
-- ============================================================

-- ──────────────────────────────────────────────────────────
-- usage_daily: add units_used and thinking_credits_used
-- ──────────────────────────────────────────────────────────
ALTER TABLE usage_daily
    ADD COLUMN IF NOT EXISTS units_used INTEGER NOT NULL DEFAULT 0;

ALTER TABLE usage_daily
    ADD COLUMN IF NOT EXISTS thinking_credits_used INTEGER NOT NULL DEFAULT 0;

-- ──────────────────────────────────────────────────────────
-- query_log: add cost_usd, units_charged, thinking_mode, detected_detailed
-- ──────────────────────────────────────────────────────────
ALTER TABLE query_log
    ADD COLUMN IF NOT EXISTS cost_usd DECIMAL(10,6) DEFAULT 0;

ALTER TABLE query_log
    ADD COLUMN IF NOT EXISTS units_charged INTEGER DEFAULT 1;

ALTER TABLE query_log
    ADD COLUMN IF NOT EXISTS thinking_mode BOOLEAN DEFAULT FALSE;

ALTER TABLE query_log
    ADD COLUMN IF NOT EXISTS detected_detailed BOOLEAN DEFAULT FALSE;

-- ──────────────────────────────────────────────────────────
-- plans: add pricing + thinking credits columns
-- ──────────────────────────────────────────────────────────
ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS price_paise_monthly INTEGER DEFAULT 0;

ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS price_paise_semester INTEGER DEFAULT 0;

ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS thinking_credits_per_day INTEGER DEFAULT 0;

-- Update plan seeds: free 10 units/40K tokens, paid 30 units/100K tokens + 1 thinking credit
UPDATE plans
SET requests_per_day = 10,
    tokens_per_day = 40000,
    thinking_credits_per_day = 0,
    price_paise_monthly = 0,
    price_paise_semester = 0
WHERE name = 'free';

UPDATE plans
SET requests_per_day = 30,
    tokens_per_day = 100000,
    thinking_credits_per_day = 1,
    price_paise_monthly = 9900,
    price_paise_semester = 44900,
    features = '{"quiz_generation": true, "longer_answers": true, "thinking_mode": true}'::jsonb
WHERE name = 'paid';

-- ──────────────────────────────────────────────────────────
-- admin_settings: key-value store for balance, premium toggle, model prices
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_by  UUID REFERENCES profiles(id)
);

-- Seed default admin settings
INSERT INTO admin_settings (key, value)
VALUES
    ('account_balance_usd', '5.0'),
    ('premium_enabled', 'false'),
    ('model_prices', '{}')
ON CONFLICT (key) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- Index on query_log for cost analytics
-- ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_query_log_cost
    ON query_log (created_at DESC) WHERE cost_usd > 0;

CREATE INDEX IF NOT EXISTS idx_query_log_thinking
    ON query_log (user_id, created_at DESC) WHERE thinking_mode = TRUE;
