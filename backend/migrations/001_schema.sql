-- ============================================================
-- College RAG Assistant — Full Schema (Phase 1)
-- Run against Supabase Postgres (pgvector must be enabled)
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- trigram similarity for FTS

-- ──────────────────────────────────────────────────────────
-- Plans (referenced by profiles)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plans (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,                       -- 'free', 'paid'
    display_name TEXT NOT NULL,
    requests_per_day INTEGER NOT NULL,
    tokens_per_day   INTEGER NOT NULL,
    features    JSONB DEFAULT '{}',                         -- e.g. {"quiz_generation": true}
    is_default  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────
-- Profiles (extends Supabase auth.users)
-- In production the FK is: REFERENCES auth.users(id) ON DELETE CASCADE
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profiles (
    id              UUID PRIMARY KEY,
    email           TEXT NOT NULL,
    full_name       TEXT,
    role            TEXT NOT NULL DEFAULT 'student'
                        CHECK (role IN ('student', 'admin')),
    department      TEXT,
    semester        INTEGER,
    roll_no         TEXT UNIQUE,
    plan_id         UUID REFERENCES plans(id),
    plan_expires_at TIMESTAMPTZ,
    is_verified     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────
-- Documents
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename              TEXT NOT NULL,
    original_filename     TEXT NOT NULL,
    department            TEXT NOT NULL,
    semester              INTEGER NOT NULL,
    subject               TEXT NOT NULL,
    academic_year         TEXT NOT NULL,            -- e.g. '2026-27'
    doc_type              TEXT NOT NULL
                              CHECK (doc_type IN ('syllabus','book','notes','previous_paper')),
    is_active             BOOLEAN DEFAULT TRUE,
    file_path             TEXT NOT NULL,
    file_size_bytes       INTEGER,
    total_pages           INTEGER,
    ingestion_status      TEXT NOT NULL DEFAULT 'queued'
                              CHECK (ingestion_status IN ('queued','processing','done','failed')),
    ingestion_error       TEXT,
    ingestion_started_at  TIMESTAMPTZ,
    ingestion_completed_at TIMESTAMPTZ,
    uploaded_by           UUID REFERENCES profiles(id),
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────
-- Chunks  (embedding = 384-dim for bge-small-en-v1.5)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content       TEXT NOT NULL,
    embedding     VECTOR(384),

    -- Denormalised metadata for fast filtered search
    semester      INTEGER NOT NULL,
    department    TEXT NOT NULL,
    subject       TEXT NOT NULL,
    academic_year TEXT NOT NULL,
    doc_type      TEXT NOT NULL,
    chapter_no    INTEGER,
    chapter_title TEXT,
    unit_no       INTEGER,
    page_start    INTEGER,
    page_end      INTEGER,
    chunk_index   INTEGER NOT NULL,
    token_count   INTEGER,

    -- Full-text search column (auto-populated by trigger)
    search_vector TSVECTOR,

    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────
-- Chapter summaries
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chapter_summaries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chapter_no    INTEGER NOT NULL,
    chapter_title TEXT,
    summary       TEXT NOT NULL,
    key_concepts  JSONB,
    model_used    TEXT NOT NULL,
    generated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chapter_no)
);

-- ──────────────────────────────────────────────────────────
-- Unit ↔ chapter mapping  (syllabus unit → book chapters)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS unit_chapter_map (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject       TEXT NOT NULL,
    semester      INTEGER NOT NULL,
    department    TEXT NOT NULL,
    academic_year TEXT NOT NULL,
    unit_no       INTEGER NOT NULL,
    unit_title    TEXT,
    chapter_no    INTEGER NOT NULL,
    chapter_title TEXT,
    document_id   UUID REFERENCES documents(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(subject, semester, department, academic_year, unit_no, chapter_no)
);

-- ──────────────────────────────────────────────────────────
-- Usage tracking (per user per day)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_daily (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES profiles(id),
    date         DATE NOT NULL DEFAULT CURRENT_DATE,
    requests_used INTEGER NOT NULL DEFAULT 0,
    tokens_used   INTEGER NOT NULL DEFAULT 0,
    cache_hits    INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- ──────────────────────────────────────────────────────────
-- Answer cache  (key = hash of normalised question + subject + sem + year)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS answer_cache (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cache_key     TEXT NOT NULL UNIQUE,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    citations     JSONB,
    subject       TEXT,
    semester      INTEGER,
    academic_year TEXT,
    hit_count     INTEGER DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    expires_at    TIMESTAMPTZ
);

-- ──────────────────────────────────────────────────────────
-- Chat sessions & messages
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES profiles(id),
    title       TEXT,
    subject     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    citations   JSONB,
    model_used  TEXT,
    tokens_used INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────
-- Query log (every request for analytics)
-- ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES profiles(id),
    session_id    UUID REFERENCES chat_sessions(id),
    question      TEXT NOT NULL,
    answer        TEXT,
    model_used    TEXT,
    provider      TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    latency_ms    INTEGER,
    cache_hit     BOOLEAN DEFAULT FALSE,
    route_type    TEXT,        -- 'llm','cache','summary','syllabus','retrieval_only'
    error         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────
-- Indexes
-- ──────────────────────────────────────────────────────────

-- Vector similarity (HNSW works on empty tables unlike IVFFlat)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_search
    ON chunks USING gin (search_vector);

-- Filtered search
CREATE INDEX IF NOT EXISTS idx_chunks_filter
    ON chunks (semester, department, subject, academic_year, doc_type);

CREATE INDEX IF NOT EXISTS idx_chunks_chapter
    ON chunks (document_id, chapter_no);

-- Active documents fast lookup
CREATE INDEX IF NOT EXISTS idx_documents_active
    ON documents (semester, department, subject, academic_year)
    WHERE is_active = TRUE;

-- Answer cache
CREATE INDEX IF NOT EXISTS idx_answer_cache_expires
    ON answer_cache (expires_at) WHERE expires_at IS NOT NULL;

-- Usage
CREATE INDEX IF NOT EXISTS idx_usage_daily_lookup
    ON usage_daily (user_id, date);

-- Query log analytics
CREATE INDEX IF NOT EXISTS idx_query_log_user
    ON query_log (user_id, created_at DESC);

-- Chat
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
    ON chat_sessions (user_id, updated_at DESC);

-- ──────────────────────────────────────────────────────────
-- Trigger: auto-populate search_vector on chunk insert/update
-- ──────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_search_vector_update ON chunks;
CREATE TRIGGER chunks_search_vector_update
    BEFORE INSERT OR UPDATE OF content ON chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_search_vector();

-- ──────────────────────────────────────────────────────────
-- Seed default plans
-- ──────────────────────────────────────────────────────────
INSERT INTO plans (name, display_name, requests_per_day, tokens_per_day, is_default, features)
VALUES
    ('free', 'Free', 10, 40000, TRUE, '{}'),
    ('paid', 'Paid', 50, 150000, FALSE, '{"quiz_generation": true, "longer_answers": true}')
ON CONFLICT (name) DO NOTHING;
