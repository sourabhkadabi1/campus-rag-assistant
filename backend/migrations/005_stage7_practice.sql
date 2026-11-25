-- ============================================================
-- College RAG Assistant — Stage 7: Practice & Quiz Generator
-- Apply after 004_phase6.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS practice_sets (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    subject       TEXT NOT NULL,
    semester      INTEGER NOT NULL,
    department    TEXT NOT NULL,
    academic_year TEXT NOT NULL,
    topic         TEXT,
    unit_no       INTEGER,
    chapter_no    INTEGER,
    question_type TEXT NOT NULL CHECK (question_type IN ('mcq', 'descriptive', 'mixed')),
    difficulty    TEXT NOT NULL DEFAULT 'medium' CHECK (difficulty IN ('easy', 'medium', 'hard')),
    questions     JSONB NOT NULL DEFAULT '[]'::jsonb,
    token_usage   INTEGER DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS practice_sets_user_idx ON practice_sets(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS practice_sets_subject_idx ON practice_sets(subject, semester, department);

CREATE TABLE IF NOT EXISTS practice_submissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practice_set_id UUID NOT NULL REFERENCES practice_sets(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    score           INTEGER,
    total           INTEGER,
    answers         JSONB NOT NULL DEFAULT '{}'::jsonb,
    completed_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS practice_submissions_user_idx ON practice_submissions(user_id, completed_at DESC);

-- Enable Row-Level Security so tables are never publicly accessible via PostgREST
ALTER TABLE public.practice_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.practice_submissions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.practice_sets FROM anon, authenticated;
REVOKE ALL ON TABLE public.practice_submissions FROM anon, authenticated;

DROP POLICY IF EXISTS "deny_public_api_access" ON public.practice_sets;
CREATE POLICY "deny_public_api_access" ON public.practice_sets
    FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS "deny_public_api_access" ON public.practice_submissions;
CREATE POLICY "deny_public_api_access" ON public.practice_submissions
    FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

