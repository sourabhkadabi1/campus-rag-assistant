-- ============================================================
-- Phase 4 — Quotas, plans, payments
-- Run AFTER 001_schema.sql
-- ============================================================

-- ──────────────────────────────────────────────────────────
-- Payments (Razorpay transactions)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(id),
    razorpay_order_id   TEXT NOT NULL UNIQUE,
    razorpay_payment_id TEXT,
    razorpay_signature  TEXT,
    plan_id             UUID REFERENCES plans(id),
    plan_name           TEXT NOT NULL,
    amount_paise        INTEGER NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'INR',
    status              TEXT NOT NULL DEFAULT 'created'
                            CHECK (status IN ('created', 'paid', 'failed', 'refunded')),
    plan_duration_days  INTEGER NOT NULL DEFAULT 30,
    plan_starts_at      TIMESTAMPTZ,
    plan_expires_at     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payments_user
    ON payments (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payments_order
    ON payments (razorpay_order_id);

-- ──────────────────────────────────────────────────────────
-- Budget guard settings (single-row config)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS budget_guard_settings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    is_enabled              BOOLEAN DEFAULT FALSE,
    threshold_pct           DECIMAL(5, 4) DEFAULT 0.9000,
    manual_retrieval_only   BOOLEAN DEFAULT FALSE,
    monthly_spend_cap_usd   DECIMAL(10, 2) DEFAULT 0,
    updated_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_by              UUID REFERENCES profiles(id)
);

-- Seed default budget guard row
INSERT INTO budget_guard_settings (is_enabled, threshold_pct, manual_retrieval_only, monthly_spend_cap_usd)
VALUES (FALSE, 0.90, FALSE, 0.00)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- Monthly spend tracking
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monthly_spend (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    month              DATE NOT NULL UNIQUE,   -- first day of month
    total_api_calls    INTEGER NOT NULL DEFAULT 0,
    total_tokens_used  BIGINT NOT NULL DEFAULT 0,
    estimated_cost_usd DECIMAL(10, 4) DEFAULT 0,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────
-- Add price column to plans (for Razorpay checkout)
-- ──────────────────────────────────────────────────────────
ALTER TABLE plans ADD COLUMN IF NOT EXISTS price_paise INTEGER DEFAULT 0;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS duration_days INTEGER DEFAULT 30;

-- Update existing paid plan with default price
UPDATE plans SET price_paise = 9900, duration_days = 30 WHERE name = 'paid' AND price_paise = 0;

-- ──────────────────────────────────────────────────────────
-- Ensure profiles has email uniqueness for abuse protection
-- ──────────────────────────────────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_email_unique
    ON profiles (email);

-- ──────────────────────────────────────────────────────────
-- Add email_verified column to profiles
-- ──────────────────────────────────────────────────────────
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS verification_token TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS verification_expires_at TIMESTAMPTZ;
