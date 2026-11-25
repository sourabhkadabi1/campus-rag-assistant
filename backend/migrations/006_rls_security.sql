-- ============================================================
-- College RAG Assistant — Supabase RLS & Security Hardening
-- Fixes Supabase Security Advisor critical issues:
--   1. rls_disabled_in_public (Table publicly accessible)
--   2. sensitive_columns_exposed (Sensitive data publicly accessible)
--   3. function_search_path_mutable (update_search_vector)
--
-- Architecture note:
--   The FastAPI backend connects via DATABASE_URL as the `postgres`
--   database owner role (which has BYPASSRLS), so all backend queries
--   continue working unchanged while PostgREST (`anon`/`authenticated`)
--   public API access is completely blocked.
-- ============================================================

DO $$
DECLARE
    tbl TEXT;
    protected_tables TEXT[] := ARRAY[
        'admin_settings',
        'answer_cache',
        'budget_guard_settings',
        'chapter_summaries',
        'chat_messages',
        'chat_sessions',
        'chunks',
        'documents',
        'monthly_spend',
        'plans',
        'practice_sets',
        'practice_submissions',
        'profiles',
        'query_log',
        'unit_chapter_map',
        'usage_daily'
    ];
BEGIN
    FOREACH tbl IN ARRAY protected_tables LOOP
        IF to_regclass(format('public.%I', tbl)) IS NOT NULL THEN
            -- 1. Enable Row-Level Security (does not restrict postgres/service_role)
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);

            -- 2. Revoke direct table privileges from PostgREST client roles
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', tbl);

            -- 3. Explicit deny-all policy for public API roles
            EXECUTE format('DROP POLICY IF EXISTS "deny_public_api_access" ON public.%I', tbl);
            EXECUTE format(
                'CREATE POLICY "deny_public_api_access" ON public.%I '
                'FOR ALL TO anon, authenticated '
                'USING (false) WITH CHECK (false)',
                tbl
            );
        END IF;
    END LOOP;
END $$;

-- Ensure payments also blocks anon completely (keeps existing authenticated SELECT policy)
DO $$
BEGIN
    IF to_regclass('public.payments') IS NOT NULL THEN
        ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON TABLE public.payments FROM anon;
        REVOKE INSERT, UPDATE, DELETE ON TABLE public.payments FROM authenticated;
    END IF;
END $$;

-- Fix function_search_path_mutable warning on trigger function
DO $$
BEGIN
    IF to_regprocedure('public.update_search_vector()') IS NOT NULL THEN
        ALTER FUNCTION public.update_search_vector() SET search_path = public, pg_temp;
    END IF;
END $$;
