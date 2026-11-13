# College RAG Assistant — Backend (Phases 1–4)

Production-grade RAG backend built with FastAPI, pgvector, and multi-model LLM routing. Grounded syllabus/textbook Q&A for college students with hybrid search, streaming SSE answers, semantic caching, rate limiting, quota enforcement, Razorpay checkout, and an automated budget guard.

---

## Architecture Overview

```
Client (/ask SSE)
  │
  ├─ 0. Abuse Rate Limiter (sliding window per-user RPM)
  ├─ 1. Query Filter Parsing (subject, chapter, unit, semester validation)
  ├─ 2. Semantic Answer Cache (SHA-256 + metadata hash, instant return)
  ├─ 3. Special Routes (precomputed chapter/unit summaries & syllabus chunks — 0 LLM calls)
  ├─ 4. Atomic Quota Consumption (pre-LLM decrement; refunds on error)
  ├─ 5. Budget Guard (at >=90% free capacity, free tier falls back to retrieval-only)
  ├─ 6. Hybrid Search (pgvector cosine + pg_trgm BM25, Reciprocal Rank Fusion)
  ├─ 7. LLM Router (priority chain: Gemini 2.5/2.0/Groq, auto 429/500 cooldown & fallback)
  └─ 8. Token Tracking & Async Query Logging
```

---

## Quick Start

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Configure environment
cp ../.env.example .env
# Edit .env — fill in DATABASE_URL, GEMINI_API_KEY, GROQ_API_KEY, etc.

# 3. Run schema migrations
python scripts/run_migrations.py

# 4. Start the server
uvicorn app.main:app --reload --port 8000

# 5. Check health
curl http://localhost:8000/health
```

---

## API Endpoints

### Core Query Pipeline
| Method | Path | Description |
|---|---|---|
| `POST` | `/ask` | Streaming SSE endpoint: filter → cache → retrieval → LLM answer + citations + quota |
| `POST` | `/chat/history` | Retrieve previous conversation turns for a session |
| `DELETE` | `/chat/{session_id}` | Clear session chat history |

### Quotas & Plans (Phase 4)
| Method | Path | Description |
|---|---|---|
| `GET` | `/quota/remaining` | Current user's daily remaining requests and tokens |
| `GET` | `/quota/usage` | Detailed usage stats (today or specific date) |
| `GET` | `/plans` | List available subscription tiers (Free, Paid) |
| `POST` | `/admin/plans` | Admin: Create a new plan tier |
| `PUT` | `/admin/plans/{name}` | Admin: Edit daily requests, token limits, or pricing |
| `DELETE` | `/admin/plans/{name}` | Admin: Deprecate or remove a plan |
| `POST` | `/admin/plans/grant` | Admin: Manually grant a paid plan to user IDs |

### Payments (Phase 4)
| Method | Path | Description |
|---|---|---|
| `POST` | `/payments/create-order` | Create a Razorpay order for paid plan checkout |
| `POST` | `/payments/webhook` | Handle Razorpay `payment.captured` webhook (HMAC-SHA256 verified) |
| `POST` | `/payments/verify` | Verify payment signature and activate plan |

### System & Admin Controls
| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/budget-guard` | Admin: Budget guard status, capacity used %, and settings |
| `POST` | `/admin/budget-guard` | Admin: Toggle exam-week mode or adjust threshold % |
| `GET` | `/admin/models` | Admin: Model status, cooldown states, and rate counters |
| `POST` | `/admin/models/{id}/toggle` | Admin: Enable/disable a specific model |
| `POST` | `/admin/models/{id}/clear-cooldown` | Admin: Clear cooldown for a model |
| `POST` | `/admin/models/reverify` | Admin: Test-probe all models in the chain |
| `POST` | `/admin/documents/upload` | Ingest PDF → chunk → embed → summarize |
| `GET` | `/admin/documents` | List documents with semester/department/subject filters |
| `GET` | `/admin/documents/{id}/status` | Detailed ingestion progress |
| `GET` | `/health` | Server health and version info |

---

## Running Tests

```bash
python -m pytest backend/tests/ -v
```

Current test suite contains **192 passing tests**:
- **test_ask.py** (17 tests): Message building, system prompts, Gemma formatting, citation deduplication.
- **test_config.py** (8 tests): Model chain parsing, token limits, summary reserves, max upload sizes.
- **test_filter_parser.py** (40 tests): Chapter/unit/semester extraction, subject matching, clean query generation, deterministic cache keys.
- **test_ingestion.py** (21 tests): Chunking, chapter heading detection, token bounds, page marker extraction.
- **test_models.py** (7 tests): Document upload metadata, validation constraints, enum definitions.
- **test_retrieval.py** (11 tests): Reciprocal Rank Fusion (RRF), scoring, ranking edge cases.
- **test_router.py** (42 tests): In-memory sliding-window rate tracking, 429/500 cooldown fallback, prompt budgeting, admin model endpoints.
- **test_summarizer.py** (5 tests): Key concepts parsing, heading detection, empty text handling.
- **test_payments.py** (11 tests): Razorpay HMAC-SHA256 verification, idempotent plan upgrades, signature tamper rejection.
- **test_plans.py** (8 tests): Plan validation, CRUD constraints, manual plan grants.
- **test_quota.py** (22 tests): Atomic `UPDATE ... RETURNING` consume, token blocking, failure refunds, budget guard throttling, 20-thread concurrency tests.

---

## Ingestion Pipeline

```
PDF Upload
  │
  ├─ 1. Text Extraction  (pdfplumber + pytesseract OCR fallback)
  ├─ 2. Chapter Detection (regex: Chapter/Unit/Module N + font-size heuristics)
  ├─ 3. Chunking          (~700 tokens, 100 overlap, respects chapter boundaries)
  ├─ 4. Embedding          (bge-small-en-v1.5, 384 dimensions, local)
  ├─ 5. Storage            (pgvector + tsvector full-text search)
  └─ 6. Summary Generation (Gemini API, one per chapter, throttled)
```

---

## Docker

```bash
cd backend
docker build -t rag-backend .
docker run -p 8000:8000 --env-file .env rag-backend
```
