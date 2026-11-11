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

# Runtime-only system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# Create uploads directory
RUN mkdir -p uploads

EXPOSE 8000

# Uvicorn with keep-alive so the free-tier container never sleeps
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "120"]
