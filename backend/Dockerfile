# ── Build stage ────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps for pdfplumber / pytesseract / Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Runtime-only system deps + curl for HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# Create uploads directory and non-root user (security hardening)
RUN mkdir -p uploads \
    && addgroup --system appgroup \
    && adduser --system --ingroup appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Container-level health check (Render/Fly.io also check /health externally)
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Uvicorn with keep-alive so the free-tier container never sleeps
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "120"]
