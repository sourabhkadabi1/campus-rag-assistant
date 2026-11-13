"""
Admin router — document upload, ingestion status, document listing,
budget guard management, margin dashboard, premium toggle, cost tracking.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from app.config import DEFAULT_MODEL_PRICES, settings
from app.database import execute, fetch, fetchrow, fetchval
from app.models import (
    AdminSettingUpdate,
    ChapterSummaryResponse,
    DocType,
    DocumentResponse,
    IngestionStatus,
    IngestionStatusResponse,
    MarginDashboardResponse,
)
from app.services.ingestion import ingest_document

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


# ── Budget guard management (Phase 4) ────────────────────────────


@router.get("/budget-guard")
async def get_budget_guard():
    """Get current budget guard status including capacity usage."""
    from app.services.quota import get_budget_guard_status
    return await get_budget_guard_status()


@router.post("/budget-guard")
async def update_budget_guard_settings(
    request: Request,
    is_enabled: bool | None = None,
    manual_retrieval_only: bool | None = None,
    threshold_pct: float | None = None,
    monthly_spend_cap_usd: float | None = None,
):
    """
    Update budget guard settings (admin only).

    Set ``manual_retrieval_only=true`` for exam-week mode (all FREE users
    get retrieval-only answers regardless of capacity).
    """
    from app.services.quota import update_budget_guard
    admin_id = request.headers.get("X-User-Id")
    result = await update_budget_guard(
        is_enabled=is_enabled,
        manual_retrieval_only=manual_retrieval_only,
        threshold_pct=threshold_pct,
        monthly_spend_cap_usd=monthly_spend_cap_usd,
        updated_by=admin_id,
    )
    return result


# ── Premium toggle (immediate effect) ────────────────────────────


@router.post("/settings/premium-toggle")
async def toggle_premium(request: Request, enabled: bool = True):
    """Toggle PREMIUM_ENABLED on/off, effective immediately."""
    admin_id = request.headers.get("X-User-Id")
    await execute(
        """INSERT INTO admin_settings (key, value, updated_at, updated_by)
           VALUES ('premium_enabled', $1, NOW(), $2)
           ON CONFLICT (key) DO UPDATE
           SET value = $1, updated_at = NOW(), updated_by = $2""",
        str(enabled).lower(), admin_id,
    )
    return {"premium_enabled": enabled}


# ── Balance management ───────────────────────────────────────────


@router.get("/settings/balance")
async def get_balance():
    """Get the current account balance."""
    from app.services.quota import get_account_balance
    balance = await get_account_balance()
    return {"account_balance_usd": balance}


@router.post("/settings/balance")
async def update_balance(request: Request, amount: float):
    """
    Set the account balance to the given amount.

    Admin should reconcile this with the real billing page periodically.
    """
    admin_id = request.headers.get("X-User-Id")
    await execute(
        """INSERT INTO admin_settings (key, value, updated_at, updated_by)
           VALUES ('account_balance_usd', $1, NOW(), $2)
           ON CONFLICT (key) DO UPDATE
           SET value = $1, updated_at = NOW(), updated_by = $2""",
        str(amount), admin_id,
    )
    return {"account_balance_usd": amount}


# ── Model pricing admin ─────────────────────────────────────────


@router.get("/settings/model-prices")
async def get_model_prices():
    """Get current model pricing configuration."""
    return {"prices": DEFAULT_MODEL_PRICES}


@router.post("/settings/model-prices")
async def update_model_prices(request: Request, prices: dict):
    """
    Update model pricing configuration.

    Expects a dict like: {"model_id": {"input": 0.30, "output": 2.50}}
    Changes are stored in admin_settings and take effect on next restart.
    """
    admin_id = request.headers.get("X-User-Id")
    await execute(
        """INSERT INTO admin_settings (key, value, updated_at, updated_by)
           VALUES ('model_prices', $1, NOW(), $2)
           ON CONFLICT (key) DO UPDATE
           SET value = $1, updated_at = NOW(), updated_by = $2""",
        json.dumps(prices), admin_id,
    )
    return {"updated": True, "prices": prices}


# ── Margin dashboard ────────────────────────────────────────────


@router.get("/margin", response_model=MarginDashboardResponse)
async def margin_dashboard():
    """
    Margin dashboard — today's and 7-day spend, remaining balance,
    estimated days left, premium/thinking spend vs cap, cache hit rate,
    detailed share, avg cost per profile, margin alert.
    """
    from app.services.quota import get_account_balance, get_today_premium_spend

    # Today's spend
    today_row = await fetchrow(
        """SELECT COALESCE(SUM(cost_usd), 0) AS total,
                  COUNT(*) FILTER (WHERE thinking_mode = TRUE) AS thinking_count
           FROM query_log
           WHERE created_at >= CURRENT_DATE AND cost_usd > 0"""
    )
    today_spend = float(today_row["total"]) if today_row else 0.0
    thinking_count = today_row["thinking_count"] if today_row else 0

    # 7-day spend
    seven_day_row = await fetchrow(
        """SELECT COALESCE(SUM(cost_usd), 0) AS total
           FROM query_log
           WHERE created_at >= CURRENT_DATE - INTERVAL '7 days' AND cost_usd > 0"""
    )
    seven_day_spend = float(seven_day_row["total"]) if seven_day_row else 0.0

    # Balance
    balance = await get_account_balance()

    # Estimated days left
    avg_daily = seven_day_spend / 7 if seven_day_spend > 0 else 0.0
    est_days = balance / avg_daily if avg_daily > 0 else 999.0

    # Premium spend today
    premium_spend = await get_today_premium_spend()

    # Cache hit rate (last 7 days)
    cache_row = await fetchrow(
        """SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE cache_hit = TRUE) AS hits
           FROM query_log
           WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'"""
    )
    total_queries = cache_row["total"] if cache_row else 0
    cache_hits = cache_row["hits"] if cache_row else 0
    cache_hit_rate = (cache_hits / total_queries) if total_queries > 0 else 0.0

    # Detailed share (last 7 days)
    detail_row = await fetchrow(
        """SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE detected_detailed = TRUE) AS detailed
           FROM query_log
           WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
             AND route_type = 'llm'"""
    )
    detail_total = detail_row["total"] if detail_row else 0
    detail_count = detail_row["detailed"] if detail_row else 0
    detailed_share = (detail_count / detail_total) if detail_total > 0 else 0.0

    # Avg cost per profile (free vs paid)
    profile_rows = await fetch(
        """SELECT
             CASE WHEN q.cost_usd = 0 THEN 'free' ELSE 'paid' END AS profile,
             AVG(q.cost_usd) AS avg_cost
           FROM query_log q
           WHERE q.created_at >= CURRENT_DATE - INTERVAL '7 days'
             AND q.route_type = 'llm'
           GROUP BY profile"""
    )
    avg_cost_per_profile = {r["profile"]: round(float(r["avg_cost"]), 6) for r in profile_rows}

    # Avg cost per paid user per month (from last 30 days)
    paid_user_row = await fetchrow(
        """SELECT COALESCE(SUM(cost_usd), 0) AS total_cost,
                  COUNT(DISTINCT user_id) AS user_count
           FROM query_log
           WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
             AND cost_usd > 0"""
    )
    paid_total = float(paid_user_row["total_cost"]) if paid_user_row else 0.0
    paid_users = paid_user_row["user_count"] if paid_user_row else 0
    avg_cost_per_paid = (paid_total / max(1, paid_users))

    # Plan price in USD (₹99/month ≈ $1.19 at ~₹83/$)
    plan_price_usd = 9900 / 83 / 100  # rough conversion

    # Margin alert: warn if avg cost per paid user > 40% of net plan price
    margin_alert = avg_cost_per_paid > (plan_price_usd * 0.40)
    alert_msg = None
    if margin_alert:
        alert_msg = (
            f"Warning: avg cost per paid user (${avg_cost_per_paid:.4f}/month) "
            f"exceeds 40% of plan price (${plan_price_usd:.2f}/month)"
        )

    return MarginDashboardResponse(
        today_spend_usd=round(today_spend, 4),
        seven_day_spend_usd=round(seven_day_spend, 4),
        remaining_balance_usd=round(balance, 2),
        estimated_days_left=round(est_days, 1),
        premium_spend_today_usd=round(premium_spend, 4),
        premium_daily_cap_usd=settings.premium_daily_spend_cap_usd,
        thinking_requests_today=thinking_count,
        cache_hit_rate=round(cache_hit_rate, 4),
        detailed_share=round(detailed_share, 4),
        avg_cost_per_profile=avg_cost_per_profile,
        avg_cost_per_paid_user_month=round(avg_cost_per_paid, 4),
        plan_price_monthly_usd=round(plan_price_usd, 2),
        margin_alert=margin_alert,
        margin_alert_message=alert_msg,
    )
