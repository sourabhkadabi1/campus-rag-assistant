"""
Pydantic models for request / response validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────


class DocType(str, Enum):
    """Allowed document types."""
    SYLLABUS = "syllabus"
    BOOK = "book"
    NOTES = "notes"
    PREVIOUS_PAPER = "previous_paper"


class IngestionStatus(str, Enum):
    """Background ingestion job states."""
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# ── Request models ────────────────────────────────────────────────


class DocumentUploadMeta(BaseModel):
    """Metadata sent alongside the PDF upload (as form fields)."""
    department: str = Field(..., min_length=1, description="e.g. 'CSE'")
    semester: int = Field(..., ge=1, le=8)
    subject: str = Field(..., min_length=1)
    academic_year: str = Field(
        ..., pattern=r"^\d{4}-\d{2,4}$", description="e.g. '2026-27'"
    )
    doc_type: DocType
    is_active: bool = True


# ── Response models ───────────────────────────────────────────────


class DocumentResponse(BaseModel):
    """Returned after upload or when listing documents."""
    id: UUID
    filename: str
    original_filename: str
    department: str
    semester: int
    subject: str
    academic_year: str
    doc_type: DocType
    is_active: bool
    file_size_bytes: Optional[int] = None
    total_pages: Optional[int] = None
    ingestion_status: IngestionStatus
    ingestion_error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestionStatusResponse(BaseModel):
    """Detailed ingestion progress for a single document."""
    document_id: UUID
    status: IngestionStatus
    total_pages: Optional[int] = None
    chunks_created: Optional[int] = None
    chapters_found: Optional[int] = None
    summaries_generated: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ChapterSummaryResponse(BaseModel):
    """A single chapter's generated summary."""
    chapter_no: int
    chapter_title: Optional[str] = None
    summary: str
    key_concepts: Optional[list[str]] = None
    model_used: str


class ModelLimitConfig(BaseModel):
    """Per-model rate-limit configuration (admin-editable)."""
    model_id: str
    rpm: int = Field(ge=0, description="Requests per minute")
    tpm: int = Field(ge=0, description="Tokens per minute")
    rpd: int = Field(ge=0, description="Requests per day")


class UnitChapterMapEntry(BaseModel):
    """A single unit ↔ chapter mapping."""
    id: UUID
    subject: str
    semester: int
    department: str
    academic_year: str
    unit_no: int
    unit_title: Optional[str] = None
    chapter_no: int
    chapter_title: Optional[str] = None
    document_id: Optional[UUID] = None

    model_config = {"from_attributes": True}


class UnitChapterMapCreate(BaseModel):
    """Request body for creating a unit-chapter mapping."""
    subject: str = Field(..., min_length=1)
    semester: int = Field(..., ge=1, le=8)
    department: str = Field(..., min_length=1)
    academic_year: str = Field(..., pattern=r"^\d{4}-\d{2,4}$")
    unit_no: int = Field(..., ge=1)
    unit_title: Optional[str] = None
    chapter_no: int = Field(..., ge=1)
    chapter_title: Optional[str] = None
    document_id: Optional[UUID] = None


# ── Phase 4: Quotas, plans, payments ─────────────────────────────


class PlanResponse(BaseModel):
    """A subscription plan returned to students or admins."""
    id: UUID
    name: str
    display_name: str
    requests_per_day: int
    tokens_per_day: int
    features: dict = Field(default_factory=dict)
    is_default: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PlanCreateRequest(BaseModel):
    """Admin request to create a new plan."""
    name: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    requests_per_day: int = Field(..., ge=1)
    tokens_per_day: int = Field(..., ge=1000)
    features: dict = Field(default_factory=dict)
    is_default: bool = False


class PlanUpdateRequest(BaseModel):
    """Admin request to update a plan."""
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    requests_per_day: Optional[int] = Field(None, ge=1)
    tokens_per_day: Optional[int] = Field(None, ge=1000)
    features: Optional[dict] = None
    is_default: Optional[bool] = None


class QuotaRemainingResponse(BaseModel):
    """Returned with every /ask response and from GET /quota/remaining."""
    requests_remaining: int
    tokens_remaining: int
    requests_limit: int
    tokens_limit: int
    requests_used: int
    tokens_used: int
    cache_hits_today: int = 0
    plan_name: str = "free"
    is_retrieval_only: bool = False
    resets_at: Optional[str] = None  # ISO 8601


class UsageResponse(BaseModel):
    """Daily usage detail."""
    date: str
    requests_used: int
    tokens_used: int
    cache_hits: int


class PlanGrantRequest(BaseModel):
    """Admin request to manually grant a plan to user(s)."""
    user_ids: list[UUID]
    plan_name: str = Field(..., min_length=1)
    duration_days: int = Field(default=30, ge=1, le=3650)


class PaymentOrderRequest(BaseModel):
    """Student request to start Razorpay checkout."""
    plan_name: str = Field(default="paid", min_length=1)


class PaymentOrderResponse(BaseModel):
    """Returned after creating a Razorpay order."""
    order_id: str
    amount_paise: int
    currency: str = "INR"
    key_id: str
    plan_name: str
    plan_display_name: str


class PaymentWebhookPayload(BaseModel):
    """Razorpay webhook payload (simplified)."""
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentRecord(BaseModel):
    """A single payment record."""
    id: UUID
    user_id: UUID
    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    plan_name: str
    amount_paise: int
    currency: str = "INR"
    status: str
    plan_starts_at: Optional[datetime] = None
    plan_expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BudgetGuardStatus(BaseModel):
    """Current global budget guard state."""
    is_active: bool
    manual_retrieval_only: bool = False
    capacity_used_pct: float
    threshold_pct: float
    free_users_affected: bool
    monthly_spend_usd: float = 0.0
    monthly_cap_usd: float = 0.0
