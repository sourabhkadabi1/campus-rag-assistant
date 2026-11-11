"""
Admin router — document upload, ingestion status, document listing.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.config import settings
from app.database import execute, fetch, fetchrow, fetchval
from app.models import (
    ChapterSummaryResponse,
    DocType,
    DocumentResponse,
    IngestionStatus,
    IngestionStatusResponse,
)
from app.services.ingestion import ingest_document

import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Upload ────────────────────────────────────────────────────────


@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    department: str = Form(...),
    semester: int = Form(...),
    subject: str = Form(...),
    academic_year: str = Form(...),
    doc_type: DocType = Form(...),
    is_active: bool = Form(True),
):
    """
    Upload a PDF and kick off background ingestion.
    Returns immediately with ingestion_status='queued'.
    """
    # ── Validate ──────────────────────────────────────────
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            413,
            f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    if not (1 <= semester <= 8):
        raise HTTPException(400, "Semester must be between 1 and 8")

    # ── Save file ─────────────────────────────────────────
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = upload_dir / safe_name
    file_path.write_bytes(content)

    # ── Insert DB record ──────────────────────────────────
    doc_id = str(uuid.uuid4())
    await execute(
        """INSERT INTO documents
           (id, filename, original_filename, department, semester,
            subject, academic_year, doc_type, is_active,
            file_path, file_size_bytes, ingestion_status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'queued')""",
        doc_id, safe_name, file.filename, department, semester,
        subject, academic_year, doc_type.value, is_active,
        str(file_path), len(content),
    )

    # ── Queue background ingestion ────────────────────────
    metadata = {
        "department": department,
        "semester": semester,
        "subject": subject,
        "academic_year": academic_year,
        "doc_type": doc_type.value,
    }
    background_tasks.add_task(ingest_document, doc_id, str(file_path), metadata)

    # ── Return document record ────────────────────────────
    row = await fetchrow("SELECT * FROM documents WHERE id=$1", doc_id)
    return _row_to_doc(row)


# ── List documents ────────────────────────────────────────────────


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    department: str | None = None,
    semester: int | None = None,
    subject: str | None = None,
):
    """List all documents, optionally filtered."""
    query = "SELECT * FROM documents WHERE TRUE"
    args: list = []
    idx = 1

    if department:
        query += f" AND department=${idx}"
        args.append(department)
        idx += 1
    if semester is not None:
        query += f" AND semester=${idx}"
        args.append(semester)
        idx += 1
    if subject:
        query += f" AND subject=${idx}"
        args.append(subject)
        idx += 1

    query += " ORDER BY created_at DESC"
    rows = await fetch(query, *args)
    return [_row_to_doc(r) for r in rows]


# ── Single document detail ────────────────────────────────────────


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str):
    row = await fetchrow("SELECT * FROM documents WHERE id=$1", doc_id)
    if not row:
        raise HTTPException(404, "Document not found")
    return _row_to_doc(row)


# ── Ingestion status ─────────────────────────────────────────────


@router.get(
    "/documents/{doc_id}/status", response_model=IngestionStatusResponse
)
async def ingestion_status(doc_id: str):
    """Detailed ingestion progress."""
    row = await fetchrow("SELECT * FROM documents WHERE id=$1", doc_id)
    if not row:
        raise HTTPException(404, "Document not found")

    chunks_count = await fetchval(
        "SELECT count(*) FROM chunks WHERE document_id=$1", doc_id
    )
    chapters_count = await fetchval(
        "SELECT count(DISTINCT chapter_no) FROM chunks WHERE document_id=$1 AND chapter_no IS NOT NULL",
        doc_id,
    )
    summaries_count = await fetchval(
        "SELECT count(*) FROM chapter_summaries WHERE document_id=$1", doc_id
    )

    return IngestionStatusResponse(
        document_id=row["id"],
        status=row["ingestion_status"],
        total_pages=row["total_pages"],
        chunks_created=chunks_count,
        chapters_found=chapters_count,
        summaries_generated=summaries_count,
        error=row["ingestion_error"],
        started_at=row["ingestion_started_at"],
        completed_at=row["ingestion_completed_at"],
    )


# ── Chapter summaries ────────────────────────────────────────────


@router.get(
    "/documents/{doc_id}/summaries",
    response_model=list[ChapterSummaryResponse],
)
async def get_summaries(doc_id: str):
    """Return generated chapter summaries for a document."""
    rows = await fetch(
        """SELECT chapter_no, chapter_title, summary, key_concepts, model_used
           FROM chapter_summaries
           WHERE document_id=$1
           ORDER BY chapter_no""",
        doc_id,
    )
    results = []
    for r in rows:
        kc = r["key_concepts"]
        if isinstance(kc, str):
            kc = json.loads(kc)
        results.append(ChapterSummaryResponse(
            chapter_no=r["chapter_no"],
            chapter_title=r["chapter_title"],
            summary=r["summary"],
            key_concepts=kc,
            model_used=r["model_used"],
        ))
    return results


# ── Toggle active status ─────────────────────────────────────────


@router.patch("/documents/{doc_id}/active")
async def toggle_active(doc_id: str, is_active: bool = True):
    """Archive or re-activate a document."""
    result = await execute(
        "UPDATE documents SET is_active=$1, updated_at=NOW() WHERE id=$2",
        is_active, doc_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "Document not found")
    return {"id": doc_id, "is_active": is_active}


# ── Delete document ──────────────────────────────────────────────


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """
    Delete a document and all its chunks / summaries (cascaded by FK).
    Also removes the uploaded file from disk.
    """
    row = await fetchrow(
        "SELECT file_path FROM documents WHERE id=$1", doc_id
    )
    if not row:
        raise HTTPException(404, "Document not found")

    # Delete from DB (chunks + summaries cascade)
    await execute("DELETE FROM documents WHERE id=$1", doc_id)

    # Best-effort file cleanup
    try:
        file_path = Path(row["file_path"])
        if file_path.exists():
            file_path.unlink()
    except Exception as exc:
        logger.warning("Could not delete file %s: %s", row["file_path"], exc)

    return {"id": doc_id, "deleted": True}


# ── Re-trigger ingestion ─────────────────────────────────────────


@router.post("/documents/{doc_id}/reingest")
async def reingest_document(
    doc_id: str, background_tasks: BackgroundTasks
):
    """
    Re-run ingestion for an existing document.
    Useful after fixing a parser bug or updating the chunking strategy.
    Existing chunks and summaries are replaced.
    """
    row = await fetchrow("SELECT * FROM documents WHERE id=$1", doc_id)
    if not row:
        raise HTTPException(404, "Document not found")

    file_path = row["file_path"]
    if not Path(file_path).exists():
        raise HTTPException(
            400, f"Source file no longer exists: {file_path}"
        )

    # Reset status
    await execute(
        """UPDATE documents
           SET ingestion_status='queued', ingestion_error=NULL,
               ingestion_started_at=NULL, ingestion_completed_at=NULL,
               updated_at=NOW()
           WHERE id=$1""",
        doc_id,
    )

    # Clear old summaries (chunks are cleared inside ingest_document)
    await execute(
        "DELETE FROM chapter_summaries WHERE document_id=$1", doc_id
    )

    metadata = {
        "department": row["department"],
        "semester": row["semester"],
        "subject": row["subject"],
        "academic_year": row["academic_year"],
        "doc_type": row["doc_type"],
    }
    background_tasks.add_task(ingest_document, doc_id, file_path, metadata)

    return {"id": doc_id, "ingestion_status": "queued", "message": "Re-ingestion queued"}


# ── Unit-Chapter Map CRUD ────────────────────────────────────────


@router.get("/unit-chapter-map")
async def list_unit_chapter_map(
    subject: str | None = None,
    semester: int | None = None,
    department: str | None = None,
):
    """List unit ↔ chapter mappings, optionally filtered."""
    query = "SELECT * FROM unit_chapter_map WHERE TRUE"
    args: list = []
    idx = 1

    if subject:
        query += f" AND subject=${idx}"
        args.append(subject)
        idx += 1
    if semester is not None:
        query += f" AND semester=${idx}"
        args.append(semester)
        idx += 1
    if department:
        query += f" AND department=${idx}"
        args.append(department)
        idx += 1

    query += " ORDER BY subject, unit_no, chapter_no"
    rows = await fetch(query, *args)
    return [dict(r) for r in rows]


@router.post("/unit-chapter-map")
async def create_unit_chapter_mapping(
    subject: str = Form(...),
    semester: int = Form(...),
    department: str = Form(...),
    academic_year: str = Form(...),
    unit_no: int = Form(...),
    unit_title: str = Form(""),
    chapter_no: int = Form(...),
    chapter_title: str = Form(""),
    document_id: str | None = Form(None),
):
    """Create a unit ↔ chapter mapping entry."""
    mapping_id = str(uuid.uuid4())
    try:
        await execute(
            """INSERT INTO unit_chapter_map
               (id, subject, semester, department, academic_year,
                unit_no, unit_title, chapter_no, chapter_title, document_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            mapping_id, subject, semester, department, academic_year,
            unit_no, unit_title or None, chapter_no, chapter_title or None,
            document_id,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                409, "This unit-chapter mapping already exists"
            )
        raise

    return {"id": mapping_id, "created": True}


@router.delete("/unit-chapter-map/{mapping_id}")
async def delete_unit_chapter_mapping(mapping_id: str):
    """Delete a unit ↔ chapter mapping."""
    result = await execute(
        "DELETE FROM unit_chapter_map WHERE id=$1", mapping_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Mapping not found")
    return {"id": mapping_id, "deleted": True}


# ── Admin: view chunks (debugging) ──────────────────────────────


@router.get("/documents/{doc_id}/chunks")
async def list_chunks(doc_id: str, limit: int = 50, offset: int = 0):
    """List chunks for a document (for debugging / verification)."""
    rows = await fetch(
        """SELECT id, chunk_index, chapter_no, chapter_title, unit_no,
                  page_start, page_end, token_count,
                  substring(content, 1, 300) AS content_preview
           FROM chunks
           WHERE document_id=$1
           ORDER BY chunk_index
           LIMIT $2 OFFSET $3""",
        doc_id, limit, offset,
    )
    total = await fetchval(
        "SELECT count(*) FROM chunks WHERE document_id=$1", doc_id
    )
    return {"total": total, "chunks": [dict(r) for r in rows]}


# ── Helpers ───────────────────────────────────────────────────────


def _row_to_doc(row) -> DocumentResponse:
    """Convert an asyncpg Record to a DocumentResponse."""
    return DocumentResponse(
        id=row["id"],
        filename=row["filename"],
        original_filename=row["original_filename"],
        department=row["department"],
        semester=row["semester"],
        subject=row["subject"],
        academic_year=row["academic_year"],
        doc_type=row["doc_type"],
        is_active=row["is_active"],
        file_size_bytes=row["file_size_bytes"],
        total_pages=row["total_pages"],
        ingestion_status=row["ingestion_status"],
        ingestion_error=row["ingestion_error"],
        created_at=row["created_at"],
    )
