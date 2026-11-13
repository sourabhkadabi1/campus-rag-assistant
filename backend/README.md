# College RAG Assistant — Backend

Production-grade RAG backend built with FastAPI, pgvector, and multi-model LLM routing. Grounded syllabus/textbook Q&A for college students with hybrid search, streaming SSE answers, semantic caching, rate limiting, dual-key quota enforcement, Thinking mode, cost tracking, Razorpay checkout, and an automated budget guard.

---

## Architecture Overview

```
Client (/ask SSE)
  │
  ├─ 0. Abuse Rate Limiter (sliding window per-user RPM)
  ├─ 1. Query Filter Parsing (subject, chapter, unit, semester validation)
  ├─ 2. Semantic Answer Cache (SHA-256 + metadata hash, instant return)
  ├─ 3. Special Routes (precomputed chapter/unit summaries & syllabus chunks — 0 LLM calls)
  ├─ 4. Detailed Question Detection (keywords + word count > 40 — 0 LLM calls)
  ├─ 5. Response Profile Selection (chunks & max_output chosen by [plan, is_detailed])
  ├─ 6. Atomic Quota & Thinking Credit Consumption (pre-LLM decrement; refunds on error)
  ├─ 7. Balance & Budget Guard (free users → retrieval-only at ≥90% capacity; paid users → retrieval-only if balance < $0.75)
  ├─ 8. Hybrid Search (pgvector cosine + pg_trgm BM25, Reciprocal Rank Fusion)
  ├─ 9. LLM Router:
  │      ├─ Free users: MODEL_CHAIN_FREE using GEMINI_API_KEY_FREE (no billing)
  │      ├─ Paid users: MODEL_CHAIN_PAID using GEMINI_API_KEY_PAID (priority queue)
  │      └─ Thinking Mode: MODEL_PREMIUM_THINKING (gemini-3.6/3.8 with thinkingBudget=2000, 5 guardrails)
  └─ 10. Per-Request Cost Tracking (USD per 1M tokens) & Balance Deduction
```

---

## Quick Start

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Configure environment
cp ../.env.example .env
# Edit .env — fill in DATABASE_URL, GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID, GROQ_API_KEY, etc.

# 3. Run schema migrations
python scripts/run_migrations.py

# 4. Start the server
uvicorn app.main:app --reload --port 8000

# 5. Check health
curl http://localhost:8000/health
```

---

## Key Features

### Dual Chains & API Key Isolation
- `GEMINI_API_KEY_FREE`: Bound to a Google Cloud project with billing disabled. Used exclusively for `MODEL_CHAIN_FREE`.
- `GEMINI_API_KEY_PAID`: Bound to a separate Google Cloud project with billing enabled. Used for `MODEL_CHAIN_PAID` and `MODEL_PREMIUM_THINKING`.
- **Key Isolation Guarantee**: Free student requests never access or consume the paid project key under any circumstance.
- **Queue Priority**: Paid requests are dequeued and served before free requests during peak traffic.

### Response Profiles & "Detailed" Detection
Automatic heuristic detection without any LLM call:
- Triggered if question contains: `in detail`, `step by step`, `derive`, `prove`, `compare`, `with example`, `write code`, `numerical`
- OR if the question contains more than 40 words.
- Chunks and token limits adapt cleanly:
  - **Free Normal**: 3 chunks, 600 max output tokens, 1 quota unit
  - **Free Detailed**: 5 chunks, 1,000 max output tokens, 2 quota units
  - **Paid Normal**: 4 chunks, 800 max output tokens, 1 quota unit
  - **Paid Detailed**: 6 chunks, 2,000 max output tokens, 2 quota units

### Thinking Mode (Paid Only)
- Explicit toggle in `/ask` requests (default: off).
- Uses `MODEL_PREMIUM_THINKING` (`gemini-3.6-flash`, `gemini-3.8-flash`) with Gemini's `thinkingConfig` (`thinkingBudget = 2000`).
- Strict guardrails: 8,000 input token cap, 4,000 total output token cap.
- Requires all 5 conditions: `PREMIUM_ENABLED = true`, active paid plan, thinking credits left today, daily spend under cap, account balance above $2.00.
- Charges 3 quota units + 1 thinking credit. Gracefully falls back to normal paid chain if busy or capped.

### Cost Tracking & Balance Guard
- Per-model pricing stored in config (USD per 1M tokens), editable in admin.
- Computes `cost_usd` per request and subtracts from `ACCOUNT_BALANCE_USD`.
- **Threshold 1 (< $2.00)**: Disables Thinking mode route.
- **Threshold 2 (< $0.75)**: Paid users switch to retrieval-only mode to prevent overages.

---

## API Endpoints

### Core Query Pipeline
| Method | Path | Description |
|---|---|---|
| `POST` | `/ask` | Streaming SSE endpoint: filter → cache → retrieval → LLM answer + citations + quota + thinking metadata |
| `POST` | `/chat/history` | Retrieve previous conversation turns for a session |
| `DELETE` | `/chat/{session_id}` | Clear session chat history |

### Quotas & Plans
| Method | Path | Description |
|---|---|---|
| `GET` | `/quota/remaining` | Current user's daily remaining units, tokens, and thinking credits |
| `GET` | `/quota/usage` | Detailed usage stats (today or specific date) |
| `GET` | `/plans` | List available subscription tiers (Free, Paid) |
| `POST` | `/admin/plans` | Admin: Create a new plan tier |
| `PUT` | `/admin/plans/{name}` | Admin: Edit daily units, token limits, or pricing |
| `DELETE` | `/admin/plans/{name}` | Admin: Deprecate or remove a plan |
| `POST` | `/admin/plans/grant` | Admin: Manually grant a paid plan to user IDs |

### Payments
| Method | Path | Description |
|---|---|---|
| `POST` | `/payments/create-order` | Create a Razorpay order for paid plan checkout (₹99/mo or ₹449/sem) |
| `POST` | `/payments/webhook` | Handle Razorpay `payment.captured` webhook (HMAC-SHA256 verified) |
| `POST` | `/payments/verify` | Verify payment signature and activate plan |

### System, Cost & Admin Controls
| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/margin` | Admin: Margin dashboard (spend, runway, cache hit rate, detailed share, margin alert) |
| `POST` | `/admin/settings/premium-toggle` | Admin: Live toggle for PREMIUM_ENABLED |
| `GET` | `/admin/settings/balance` | Admin: View current account balance |
| `POST` | `/admin/settings/balance` | Admin: Update/reconcile account balance with billing console |
| `GET` | `/admin/settings/model-prices` | Admin: View per-model token pricing |
| `POST` | `/admin/settings/model-prices` | Admin: Update model pricing |
| `GET` | `/admin/budget-guard` | Admin: Budget guard status, capacity used %, and settings |
| `POST` | `/admin/budget-guard` | Admin: Toggle exam-week mode or adjust threshold % |
| `GET` | `/admin/models/status` | Admin: Model status, cooldown states, and rate counters |
| `POST` | `/admin/models/{id}/toggle` | Admin: Enable/disable a specific model |
| `POST` | `/admin/models/{id}/clear-cooldown` | Admin: Clear cooldown for a model |
| `POST` | `/admin/models/reverify` | Admin: Test-probe all models in the chains |
| `POST` | `/admin/documents/upload` | Ingest PDF → chunk → embed → summarize |
| `GET` | `/admin/documents` | List documents with semester/department/subject filters |
| `GET` | `/admin/documents/{id}/status` | Detailed ingestion progress |
| `GET` | `/health` | Server health and version info |

---

## Running Tests

```bash
python -m pytest backend/tests/ -v
```

Current test suite contains **212 passing tests**:
- **test_redesign.py** (20 tests): Dual chains, API key isolation, detailed detection, response profiles, thinking mode conditions, thinking caps, balance guard thresholds, cost calculation, atomic units & credits.
- **test_ask.py** (17 tests): Message building, system prompts, Gemma formatting, citation deduplication.
- **test_config.py** (8 tests): Model chain parsing, token limits, summary reserves, max upload sizes.
- **test_filter_parser.py** (40 tests): Chapter/unit/semester extraction, subject matching, clean query generation, deterministic cache keys.
- **test_ingestion.py** (21 tests): Chunking, chapter heading detection, token bounds, page marker extraction.
- **test_models.py** (7 tests): Document upload metadata, validation constraints, enum definitions.
- **test_retrieval.py** (11 tests): Reciprocal Rank Fusion (RRF), scoring, ranking edge cases.
- **test_router.py** (38 tests): In-memory sliding-window rate tracking, 429/500 cooldown fallback, prompt budgeting, admin model endpoints.
- **test_summarizer.py** (5 tests): Key concepts parsing, heading detection, empty text handling.
- **test_payments.py** (11 tests): Razorpay HMAC-SHA256 verification, idempotent plan upgrades, signature tamper rejection.
- **test_plans.py** (8 tests): Plan validation, CRUD constraints, manual plan grants.
- **test_quota.py** (27 tests): Atomic `UPDATE ... RETURNING` consume, unit consumption, token blocking, failure refunds, budget guard throttling, concurrency tests.

---

## Docker

```bash
cd backend
docker build -t rag-backend .
docker run -p 8000:8000 --env-file .env rag-backend
```
