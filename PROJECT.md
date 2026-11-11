# PROJECT: College RAG Assistant

## GOAL
A web app where college students (about 500 registered, ~150 active per day) ask questions about their current semester's syllabus and books, and get answers grounded ONLY in admin-uploaded documents, with citations. Must be fast, polished-looking, secure, and survive free-tier API limits.

## RULES FOR YOU (the coding agent)
- Work ONLY on the phase I name. Stop at the end of it and tell me how to test it.
- Do not read node_modules, .next, data/, uploads/ or large files. Open only the files you need.
- Never hardcode API keys, model names, limits or prices. Everything comes from .env or an admin settings table.
- Write clean, typed, commented code with error handling and basic tests for the critical logic (router, quota, filter parsing).
- Never commit .env. Create .env.example and a .gitignore that covers .env, node_modules, .next, data, uploads.

## STACK
- Backend: Python, FastAPI (async), httpx, Pydantic.
- Database/auth/vector search: Supabase (Postgres + pgvector + full-text search + Auth).
- Cache/counters/queue: Redis (Upstash free tier or local Redis in dev). Abstract it so an in-memory fallback works in dev.
- Embeddings: local sentence-transformers model bge-small (no API cost).
- Frontend: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Framer Motion.
- Deploy: Vercel (frontend), Render or Fly.io (backend, with keep-alive so it never sleeps), Dockerfile for backend.

## ENV VARIABLES (create .env.example with all of these, no real values)
GEMINI_API_KEY, GROQ_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, REDIS_URL

```
# Student answers, in priority order (my chosen order)
MODEL_CHAIN=gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash-lite,gemini-3.6-flash,gemini-3.8-flash,gemma-4-26b,gemma-4-31b,groq:openai/gpt-oss-20b

# Chapter summaries at upload time: strong Flash models first
SUMMARY_MODEL=gemini-3.6-flash
SUMMARY_FALLBACK=gemini-3.8-flash

# Quota reserved for summaries (the Flash models allow only 20 requests/day each).
# The student chain must NOT use the last N requests/day of these models.
SUMMARY_RESERVE_RPD=10
```

Per-model limits (editable in config/admin, never hardcoded). Seed values from my AI Studio / Groq dashboards:

| Model | RPM | TPM | RPD |
|---|---|---|---|
| gemini-3.5-flash-lite | 15 | 250000 | 500 |
| gemini-3.1-flash-lite | 15 | 250000 | 500 |
| gemini-2.5-flash-lite | 10 | 250000 | 20 |
| gemini-3.6-flash | 5 | 250000 | 20 |
| gemini-3.8-flash | 5 | 250000 | 20 |
| gemma-4-26b | 30 | 16000 | 14400 |
| gemma-4-31b | 30 | 16000 | 14400 |
| groq: openai/gpt-oss-20b | 30 | 8000 | 1000 |

NOTE ON IDs: `gemini-3.5-flash-lite`, `gemini-2.5-flash-lite` and the Groq ID `openai/gpt-oss-20b` are confirmed. The other Gemini IDs are best guesses from naming patterns, and the Gemma IDs may need suffixes. The startup verification in Phase 3 resolves this. Limits change often, so they must be editable without code changes.

---------------------------------------------------------------

## PHASE 1 - Database + ingestion (admin)
1. Create the schema (SQL migrations): profiles (role student/admin, department, semester, roll_no, plan, plan_expires_at), documents, chunks (with embedding vector, semester, department, subject, academic_year, doc_type, chapter_no, chapter_title, unit_no, page), chapter_summaries, unit_chapter_map (syllabus unit -> book chapters), usage_daily, answer_cache, plans, chat_sessions, chat_messages, query_log.
2. Admin upload endpoint: PDF + metadata (department, semester, subject, academic_year, doc_type = syllabus | book | notes | previous_paper, is_active).
3. Background ingestion job with status (queued, processing, done, failed):
   - extract text per page (pdfplumber/PyMuPDF), OCR fallback (pytesseract) for scanned pages
   - detect chapter/unit headings with regex + font-size heuristics; store chapter_no/title/page on every chunk
   - chunk by section (~600-800 tokens, 100 overlap), keep tables/code blocks intact where possible
   - embed with bge-small, store in pgvector, add a full-text search column
4. After indexing, auto-generate ONE summary + key-concepts sheet per chapter using SUMMARY_MODEL (fallback SUMMARY_FALLBACK). Store in chapter_summaries. Regenerate only if the document is re-uploaded. Throttle these calls (low daily limits) and respect SUMMARY_RESERVE_RPD.
5. Versioning: documents have academic_year and is_active; only active documents are searched. Old ones stay archived.
6. Write scripts/list_models.py (see Phase 3, step 0) early, so I can fetch the exact model IDs.

Deliver: working admin API + a script to ingest a sample PDF + how to test.

## PHASE 2 - Query pipeline
1. Student identity: semester and department come from the authenticated profile on the server. Never trust semester from the request body.
2. Filter parsing WITHOUT any LLM call: regex/rules for "sem 3", "semester 3", "chapter 2", "ch 2", "unit 4", "module 3", and subject names/aliases from the subjects table. Map unit -> chapters using unit_chapter_map. Output {subject, chapter, unit, clean_query}.
3. Retrieval: hybrid search (pgvector similarity + Postgres full-text), filtered by the student's semester/department/active documents and parsed subject/chapter. Merge with reciprocal rank fusion. If chapter-filtered search returns nothing relevant, retry across the whole semester and tell the student where the answer was found ("not in Chapter 2, found in Chapter 4").
4. Special routes that cost ZERO LLM calls:
   - "explain/summarize chapter X", "key points of unit Y" -> serve stored chapter_summaries.
   - "what is in unit 2", "syllabus of ..." -> answer directly from syllabus chunks/data.
   - Exact repeated question -> answer_cache (key = normalized question + subject + semester + academic_year; TTL configurable). Cache hits never consume quota.
5. LLM answering (exactly ONE LLM call per uncached question):
   - One short shared system prompt used by ALL models: answer ONLY from the provided context, cite sources as [Book, Chapter, Page], say "I couldn't find this in your course material" if context is insufficient, never invent citations, concise exam-friendly style, render equations in LaTeX. If a model handles system prompts poorly (e.g. Gemma), send the same text at the top of the user message instead.
   - Retrieve 3-4 chunks normally (max 6 for "detailed" requests). Keep the prompt small. Keep only the last 2 chat turns as history.
   - Cap max_output_tokens (~800 normal, ~2000 detailed). Keep thinking budget low/off.
   - Stream the answer via Server-Sent Events, then send the citations as a final event.
6. Log every request in query_log: user, model used, provider, input/output tokens (from real API usage metadata), latency, cache hit, route type.

Deliver: /ask endpoint (SSE), tests for filter parsing, test for the "not found" behaviour.

## PHASE 3 - LLM router (free tiers, automatic fallback)
0. Model ID verification (do this first):
   - Write scripts/list_models.py that calls the Gemini "list models" endpoint with GEMINI_API_KEY and the Groq "list models" endpoint with GROQ_API_KEY, and prints all available model IDs.
   - At backend startup, compare every entry in MODEL_CHAIN, SUMMARY_MODEL and SUMMARY_FALLBACK against those lists. For any ID not found: log a clear error, suggest the closest matching ID from the list (e.g. a Gemma ID with a suffix), and automatically exclude that model from the chain instead of crashing.
   - Add an admin page showing each configured model as "verified" or "ID not found", so I can fix .env without touching code.
   - Never let an unverified model be called during a student request.
1. Provider abstraction with adapters: Gemini API (also serves Gemma models) and Groq (OpenAI-compatible). Easy to add OpenRouter or a self-hosted model later.
2. Router walks MODEL_CHAIN in order and picks the first AVAILABLE model:
   - unavailable if in cooldown (after a 429: ~60s for per-minute limits, until reset for daily limits; after a 5xx: ~15s)
   - unavailable if our own counters show >=95% of its RPD, or it would exceed its RPM/TPM this minute (track tokens per minute in Redis with a sliding window)
   - for models listed in SUMMARY_MODEL / SUMMARY_FALLBACK, the student chain may only use requests up to (rpd - SUMMARY_RESERVE_RPD); the remainder is reserved for the summary job
   - on 429/5xx: mark cooldown, immediately try the next model
3. Per-model prompt budgeting: when the chosen model has a small TPM (Gemma ~16K, Groq ~8K), automatically shrink the prompt (fewer chunks, shorter history, lower max_output_tokens).
4. Request queue: if all models are busy, queue the request, retry with exponential backoff, and push the student's queue position over SSE ("You're #3, about 10s"). Timeout after ~60s with a friendly message and the retrieval-only fallback.
5. Counters live in Redis (not in memory) so they survive restarts. Daily counters reset at the provider's reset time (configurable timezone).
6. Admin endpoint to view each model's status (available / cooling down / used today) and to enable/disable models live.
7. Tests: simulate 429 on the first model and verify fallback; simulate all models busy and verify queue + retrieval-only fallback.

## PHASE 4 - Quotas, plans, payments
1. Quota check happens BEFORE the LLM call, atomically (single SQL UPDATE ... WHERE requests_used < limit RETURNING, or Redis INCR with expiry). If the LLM call fails, refund the count. Cache hits and stored-summary routes do not consume quota.
2. Track both requests_used and tokens_used per user per day (use real usage from the API response). Block when either limit is reached. A student may slightly overshoot on their last question.
3. Plans table, editable in admin without code. Defaults: Free = 10 requests and 40,000 tokens/day. Paid = 50 requests and 150,000 tokens/day plus extras (quiz generation, longer answers).
4. Show remaining quota in the UI ("7 questions left today").
5. Global budget guard: when combined free provider capacity is ~90% used, FREE users automatically switch to retrieval-only mode (top passages with page numbers, no generated answer) while PAID users keep full answers. Admin can also toggle this manually (exam-week mode).
6. Payments: Razorpay checkout + webhook (verify signature) that sets plan and plan_expires_at. Admin can grant paid status manually or in bulk (e.g. if the college pays). Expired plans fall back to Free automatically.
7. Abuse protection: per-user per-minute rate limit, one account per college email/roll number, email verification, request size limits, basic bot protection on signup.
8. Optional hard monthly spend cap setting for any paid API usage.

Deliver: quota tests (concurrent requests cannot exceed the limit), admin screens for plans/limits.

## PHASE 5 - Frontend (must look premium, not basic)
1. Design: modern, clean, branded; dark + light mode; smooth Framer Motion transitions; fully mobile-first and responsive; good empty/loading/error states; accessible.
2. Student app: login/signup (college email), profile with department + semester, chat UI with streaming tokens, markdown + KaTeX equations + syntax-highlighted code, copy button, source cards that open the PDF at the cited page, subject/chapter sidebar showing only the student's semester, quick actions (Summarize chapter, Key concepts, Quiz me), chat history, remaining-quota indicator, queue-position indicator, and a clear message when in retrieval-only mode.
3. Privacy notice: free-tier prompts may be used by the model provider to improve their products; do not enter personal information.
4. Admin dashboard: document upload + metadata form, ingestion status, chapter/unit mapping editor, user and plan management, model status panel (Phase 3), usage analytics (questions/day, cache hit rate, tokens, cost estimate, most asked topics, unanswered questions list).

Deliver: all screens working against the real backend.

## PHASE 6 - Security, hardening, deploy
1. Server-side authorization on every endpoint (students can only query their own semester/department; admin routes admin-only). Use Supabase Row Level Security where applicable.
2. Validate and sanitize uploads (type, size). Treat document text as untrusted: the system prompt must resist instructions embedded in documents ("ignore previous instructions").
3. Structured logging, error tracking hook (Sentry-ready), health endpoint, graceful shutdown.
4. Dockerfile for backend, deploy configs for Vercel + Render/Fly, keep-alive ping so the free backend does not sleep, environment variable documentation.
5. Evaluation script: 30 sample Q&A pairs (I will provide); report retrieval hit rate, citation correctness, "I don't know" correctness, and latency PER MODEL in the chain, so I can reorder the chain by quality.
6. README: setup, env vars, how to ingest, how to add a model/provider, how to change limits, how to run tests, how to deploy.

## DEFINITION OF DONE
- A Sem-3 student asking "in chapter 2 explain normalization" gets a grounded, cited answer from their semester's material only; asking about another semester returns nothing from it.
- Disabling the first model (wrong ID) makes the router fall to the next with no visible error.
- A free user over quota is blocked server-side; a cached or summary answer costs no quota.
- When all models are busy, the student sees queue position, then the retrieval-only fallback.
- Every model in MODEL_CHAIN shows "verified" in the admin model page before launch.
