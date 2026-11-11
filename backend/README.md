# College RAG Assistant — Backend (Phase 1)

Admin API for document ingestion: upload PDFs → extract text → detect chapters → chunk → embed (bge-small) → store in pgvector → auto-generate chapter summaries.

## Quick Start

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Configure environment
cp ../.env.example .env
# Edit .env — fill in at least DATABASE_URL

# 3. Run schema migrations
python scripts/run_migrations.py

# 4. Start the server
uvicorn app.main:app --reload --port 8000

# 5. Check health
curl http://localhost:8000/health
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | Postgres connection string (Supabase pooler) |
| `GEMINI_API_KEY` | For summaries | Gemini API key (for chapter summary generation) |
| `GROQ_API_KEY` | Phase 3 | Groq API key |
| `SUPABASE_URL` | Phase 2+ | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Phase 2+ | Supabase service role key |
| `REDIS_URL` | Phase 3+ | Redis/Upstash URL |
| `MODEL_CHAIN` | Phase 3 | Comma-separated model IDs in priority order |
| `SUMMARY_MODEL` | Optional | Model for chapter summaries (default: `gemini-3.6-flash`) |
| `SUMMARY_FALLBACK` | Optional | Fallback summary model (default: `gemini-3.8-flash`) |
| `SUMMARY_RESERVE_RPD` | Optional | RPD reserved for summaries (default: `10`) |
| `EMBEDDING_MODEL` | Optional | sentence-transformers model (default: `BAAI/bge-small-en-v1.5`) |

## API Endpoints

### Admin

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/documents/upload` | Upload PDF + metadata → queues ingestion |
| `GET` | `/admin/documents` | List documents (filter by department/semester/subject) |
| `GET` | `/admin/documents/{id}` | Get single document |
| `GET` | `/admin/documents/{id}/status` | Detailed ingestion progress |
| `GET` | `/admin/documents/{id}/summaries` | Chapter summaries for a document |
| `GET` | `/admin/documents/{id}/chunks` | Browse chunks (for debugging) |
| `PATCH` | `/admin/documents/{id}/active` | Archive / re-activate |
| `DELETE` | `/admin/documents/{id}` | Delete document + file + chunks |
| `POST` | `/admin/documents/{id}/reingest` | Re-run ingestion pipeline |
| `GET` | `/admin/unit-chapter-map` | List unit ↔ chapter mappings |
| `POST` | `/admin/unit-chapter-map` | Create a mapping |
| `DELETE` | `/admin/unit-chapter-map/{id}` | Delete a mapping |

### System

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |

## Running Tests

```bash
cd backend
pytest -v
```

Tests cover (no DB required):
- Chapter heading detection (regex patterns, font heuristics, dedup)
- Text chunking (boundaries, overlap, token bounds, page markers)
- Token estimation
- Config parsing (MODEL_CHAIN, limits, defaults)
- Pydantic model validation (semester bounds, doc types, academic year)
- Summary key-concepts extraction

## Ingestion Pipeline

```
PDF Upload
  │
  ├─ 1. Text Extraction  (pdfplumber + pytesseract OCR fallback)
  ├─ 2. Chapter Detection (regex: Chapter/Unit/Module N + font-size gate)
  ├─ 3. Chunking          (~700 tokens, 100 overlap, respects chapter boundaries)
  ├─ 4. Embedding          (bge-small-en-v1.5, 384 dimensions, local)
  ├─ 5. Storage            (pgvector + tsvector full-text search)
  └─ 6. Summary Generation (Gemini API, one per chapter, throttled)
```

## Scripts

| Script | Description |
|---|---|
| `scripts/run_migrations.py` | Apply SQL schema to the database |
| `scripts/list_models.py` | Discover Gemini + Groq model IDs |
| `scripts/ingest_sample.py` | Ingest a PDF via API or direct pipeline |
| `scripts/keep_alive.py` | Ping /health to prevent free-tier sleep |

## Docker

```bash
cd backend
docker build -t rag-backend .
docker run -p 8000:8000 --env-file .env rag-backend
```
