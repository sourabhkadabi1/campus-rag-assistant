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
