# Deployment Guide — College RAG Assistant

This guide covers deploying the full stack: **Backend** (FastAPI on Render or Fly.io), **Frontend** (Next.js on Vercel), and **Database** (Supabase Postgres + pgvector).

---

## Prerequisites

| Service | Purpose | Free tier? |
|---|---|---|
| [Supabase](https://supabase.com) | Postgres + pgvector + Auth | ✓ |
| [Render](https://render.com) **or** [Fly.io](https://fly.io) | Backend hosting | ✓ |
| [Vercel](https://vercel.com) | Frontend hosting | ✓ |
| [Upstash](https://upstash.com) | Redis (rate counters) | ✓ |
| [Sentry](https://sentry.io) | Error tracking (optional) | ✓ |

---

## 1. Database — Supabase

1. Create a new Supabase project.
2. Enable the **pgvector** extension:  
   Dashboard → Database → Extensions → search "vector" → Enable.
3. Run the schema migrations **in order**:
   ```
   backend/migrations/001_schema.sql
   backend/migrations/002_phase4.sql
   backend/migrations/003_redesign.sql
   backend/migrations/004_phase6.sql
   ```
   Paste each file into the Supabase SQL Editor and execute.
4. Copy the **Connection string (URI)** from Settings → Database → Connection string.
   This is your `DATABASE_URL`.

---

## 2. Redis — Upstash

1. Create a free Redis database at [Upstash](https://console.upstash.com).
2. Copy the **Redis REST URL** (or the `redis://...` connection string).
   This is your `REDIS_URL`.

---

## 3. Backend — Option A: Render

1. Push your code to a GitHub repo.
2. In the Render dashboard, create a **New Web Service** → Docker.
3. Set **Root Directory** to `backend`, or use the Blueprint:
   ```bash
   # From repo root
   render blueprint apply
   ```
4. Add environment variables in Render dashboard:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `postgresql://…` from Supabase |
   | `REDIS_URL` | `redis://…` from Upstash |
   | `GEMINI_API_KEY_FREE` | Your free-tier Gemini API key |
   | `GEMINI_API_KEY_PAID` | Your paid-tier Gemini API key |
   | `GROQ_API_KEY` | Your Groq API key |
   | `ADMIN_USERNAME` | Admin login username |
   | `ADMIN_PASSWORD` | Admin login password |
   | `RAZORPAY_KEY_ID` | Razorpay key (optional) |
   | `RAZORPAY_KEY_SECRET` | Razorpay secret (optional) |
   | `SENTRY_DSN` | Sentry DSN (optional) |
   | `LOG_FORMAT` | `json` |
   | `ENVIRONMENT` | `production` |

5. Set **Health Check Path** to `/health`.
6. Deploy. First deploy takes ~5 min (downloads the embedding model).

### Keep-alive (Render free tier)

Render free-tier services sleep after 15 min of inactivity.
Run the keep-alive script from any always-on machine or a GitHub Action:

```bash
python backend/scripts/keep_alive.py --url https://your-backend.onrender.com
```

---

## 3. Backend — Option B: Fly.io

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/).
2. From the repo root:
   ```bash
   fly auth login
   fly launch --config fly.toml --dockerfile backend/Dockerfile --no-deploy
   ```
3. Set secrets:
   ```bash
   fly secrets set DATABASE_URL="postgresql://…"
   fly secrets set REDIS_URL="redis://…"
   fly secrets set GEMINI_API_KEY_FREE="…"
   fly secrets set GEMINI_API_KEY_PAID="…"
   fly secrets set GROQ_API_KEY="…"
   fly secrets set ADMIN_USERNAME="…"
   fly secrets set ADMIN_PASSWORD="…"
   # Optional:
   fly secrets set SENTRY_DSN="…"
   fly secrets set RAZORPAY_KEY_ID="…"
   fly secrets set RAZORPAY_KEY_SECRET="…"
   ```
4. Create a persistent volume for uploads:
   ```bash
   fly volumes create uploads --size 1 --region bom
   ```
5. Deploy:
   ```bash
   fly deploy
   ```

---

## 4. Frontend — Vercel

1. Import the repo in [Vercel](https://vercel.com/import).
2. Set **Root Directory** to `frontend`.
3. Set **Framework Preset** to Next.js.
4. Add environment variable:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://your-backend.onrender.com` (or Fly URL) |

5. Deploy. Vercel auto-deploys on every push to `main`.
6. Security headers are configured in `frontend/vercel.json`.

---

## 5. Post-Deploy Checklist

- [ ] Open `https://your-backend/health` — verify all checks pass.
- [ ] Open `https://your-backend/docs` — Swagger UI loads.
- [ ] Log into admin dashboard with your `ADMIN_USERNAME` / `ADMIN_PASSWORD`.
- [ ] Upload a sample PDF and verify ingestion completes (`status: done`).
- [ ] Ask a question from the student UI and verify grounded answer.
- [ ] Run the evaluation suite:
  ```bash
  python backend/scripts/evaluate_rag.py --url https://your-backend
  ```
- [ ] Verify Sentry receives a test error (if configured).
- [ ] Set up keep-alive if on Render free tier.

---

## 6. Updating

```bash
# Pull latest code
git pull origin main

# Render: auto-deploys on push
# Fly.io: manual deploy
fly deploy

# Run new migrations in Supabase SQL Editor if any
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Backend sleeps (Render free) | Run `keep_alive.py` as a cron / GitHub Action |
| Embedding model OOM | Use `shared-cpu-1x` with 512 MB+ RAM on Fly |
| `DATABASE_URL` connection refused | Check Supabase connection pooler URL; use port `6543` for pooled mode |
| CORS errors in browser | Verify `NEXT_PUBLIC_API_URL` matches the actual backend URL |
| PDF upload fails with "not a valid PDF" | Ensure the file is a real PDF (starts with `%PDF-`), not a renamed image |
