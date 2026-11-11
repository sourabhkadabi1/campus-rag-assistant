#!/usr/bin/env python3
"""
Ingest a sample PDF through the admin API.

Usage:
    # With the server running (uvicorn app.main:app):
    python scripts/ingest_sample.py path/to/sample.pdf --department CSE --semester 3 --subject DBMS --year 2026-27 --type book

    # Without the server (direct pipeline — requires DATABASE_URL):
    python scripts/ingest_sample.py path/to/sample.pdf --direct --department CSE --semester 3 --subject DBMS --year 2026-27 --type book
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def via_api(args: argparse.Namespace) -> None:
    """Upload via the running FastAPI server."""
    import httpx

    url = f"{args.base_url}/admin/documents/upload"
    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"ERROR: file not found: {pdf}")
        sys.exit(1)

    print(f"Uploading {pdf.name} to {url} …")

    with open(pdf, "rb") as f:
        resp = httpx.post(
            url,
            files={"file": (pdf.name, f, "application/pdf")},
            data={
                "department": args.department,
                "semester": str(args.semester),
                "subject": args.subject,
                "academic_year": args.year,
                "doc_type": args.type,
                "is_active": "true",
            },
            timeout=120,
        )

    if resp.status_code != 200:
        print(f"ERROR {resp.status_code}: {resp.text}")
        sys.exit(1)

    doc = resp.json()
    doc_id = doc["id"]
    print(f"✓ Document created: {doc_id}")
    print(f"  Status: {doc['ingestion_status']}")
    print()

    # Poll ingestion status
    print("Polling ingestion status …")
    status_url = f"{args.base_url}/admin/documents/{doc_id}/status"
    for _ in range(120):
        time.sleep(2)
        sr = httpx.get(status_url, timeout=30)
        if sr.status_code != 200:
            continue
        st = sr.json()
        status = st["status"]
        print(f"  {status}  chunks={st.get('chunks_created',0)}  "
              f"chapters={st.get('chapters_found',0)}  "
              f"summaries={st.get('summaries_generated',0)}")
        if status in ("done", "failed"):
            break
    else:
        print("  (timed out waiting)")

    print("\nDone.")


async def via_direct(args: argparse.Namespace) -> None:
    """Run the ingestion pipeline directly (no server needed)."""
    from dotenv import load_dotenv
    load_dotenv()

    from app.database import init_db, close_db
    from app.services.embeddings import load_model
    from app.services.ingestion import ingest_document

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"ERROR: file not found: {pdf}")
        sys.exit(1)

    print("Connecting to database …")
    await init_db()

    print("Loading embedding model …")
    load_model()

    import uuid
    from app.database import execute

    doc_id = str(uuid.uuid4())
    print(f"Creating document record {doc_id} …")
    await execute(
        """INSERT INTO documents
           (id, filename, original_filename, department, semester,
            subject, academic_year, doc_type, is_active,
            file_path, file_size_bytes, ingestion_status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'queued')""",
        doc_id, pdf.name, pdf.name, args.department, args.semester,
        args.subject, args.year, args.type, True,
        str(pdf), pdf.stat().st_size,
    )

    metadata = {
        "department": args.department,
        "semester": args.semester,
        "subject": args.subject,
        "academic_year": args.year,
        "doc_type": args.type,
    }

    print("Running ingestion pipeline …\n")
    await ingest_document(doc_id, str(pdf), metadata)

    print(f"\n✓ Document {doc_id} ingested.")
    await close_db()


def main():
    p = argparse.ArgumentParser(description="Ingest a sample PDF")
    p.add_argument("pdf", help="Path to the PDF file")
    p.add_argument("--department", required=True)
    p.add_argument("--semester", type=int, required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--year", required=True, help="e.g. 2026-27")
    p.add_argument("--type", default="book",
                    choices=["syllabus", "book", "notes", "previous_paper"])
    p.add_argument("--direct", action="store_true",
                    help="Run pipeline directly (no server needed)")
    p.add_argument("--base-url", default="http://localhost:8000",
                    help="Server base URL (ignored with --direct)")

    args = p.parse_args()

    if args.direct:
        asyncio.run(via_direct(args))
    else:
        via_api(args)


if __name__ == "__main__":
    main()
