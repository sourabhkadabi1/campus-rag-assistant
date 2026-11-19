-- ============================================================
-- College RAG Assistant — Phase 6 Schema Hardening
-- Apply after 003_redesign.sql
-- ============================================================

-- ── Add email verification columns to profiles ─────────────
-- (abuse.py uses these; may already exist in some deployments)
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS email_verified       BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS verification_token   TEXT,
    ADD COLUMN IF NOT EXISTS verification_expires_at TIMESTAMPTZ;

-- ── Add slides_pdf to the doc_type check constraint ────────
-- Drop old constraint (name may vary; use the generic approach)
ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_doc_type_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_doc_type_check
    CHECK (doc_type IN ('syllabus', 'book', 'notes', 'previous_paper', 'slides_pdf'));

-- ── thinking_credits_per_day on plans ──────────────────────
ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS thinking_credits_per_day INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS price_paise              INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS duration_days            INTEGER NOT NULL DEFAULT 30;

-- ── payments table (required by payment.py) ────────────────
CREATE TABLE IF NOT EXISTS payments (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES profiles(id),
    razorpay_order_id    TEXT NOT NULL UNIQUE,
    razorpay_payment_id  TEXT,
    razorpay_signature   TEXT,
    plan_id              UUID REFERENCES plans(id),
    plan_name            TEXT NOT NULL,
    amount_paise         INTEGER NOT NULL,
    currency             TEXT NOT NULL DEFAULT 'INR',
    status               TEXT NOT NULL DEFAULT 'created'
                             CHECK (status IN ('created', 'paid', 'failed', 'refunded')),
    plan_starts_at       TIMESTAMPTZ,
    plan_expires_at      TIMESTAMPTZ,
    plan_duration_days   INTEGER NOT NULL DEFAULT 30,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS payments_user_id_idx ON payments(user_id);
CREATE INDEX IF NOT EXISTS payments_order_id_idx ON payments(razorpay_order_id);

-- ── query_log additions ─────────────────────────────────────
ALTER TABLE query_log
    ADD COLUMN IF NOT EXISTS thinking_mode       BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS detected_detailed   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cost_usd            NUMERIC(12,8) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS units_charged       INTEGER DEFAULT 1;

-- ── usage_daily additions ──────────────────────────────────
ALTER TABLE usage_daily
    ADD COLUMN IF NOT EXISTS units_used              INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS thinking_credits_used   INTEGER NOT NULL DEFAULT 0;

-- ── answer_cache: add department column for cache-key v7 ───
ALTER TABLE answer_cache
    ADD COLUMN IF NOT EXISTS department TEXT;

-- ── Index for fast quota lookups ────────────────────────────
CREATE INDEX IF NOT EXISTS usage_daily_user_date_idx
    ON usage_daily (user_id, date DESC);

-- ── Seed default plans (idempotent) ────────────────────────
INSERT INTO plans (name, display_name, requests_per_day, tokens_per_day,
                   thinking_credits_per_day, price_paise, duration_days,
                   is_default, features)
VALUES
    ('free', 'Free Plan', 10, 40000, 0, 0, 30, TRUE,
     '{"quiz_generation": false}'),
    ('paid', 'Premium Plan', 30, 100000, 1, 9900, 30, FALSE,
     '{"quiz_generation": true, "priority_queue": true}')
ON CONFLICT (name) DO NOTHING;
