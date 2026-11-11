"""
Tests for Pydantic request/response models.
Validates constraints, enums, and serialisation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import DocType, DocumentUploadMeta, IngestionStatus


class TestDocumentUploadMeta:
    def test_valid(self):
        m = DocumentUploadMeta(
            department="CSE",
            semester=3,
            subject="DBMS",
            academic_year="2026-27",
            doc_type=DocType.BOOK,
        )
        assert m.department == "CSE"
        assert m.is_active is True  # default

    def test_semester_bounds(self):
        with pytest.raises(ValidationError):
            DocumentUploadMeta(
                department="CSE", semester=0, subject="X",
                academic_year="2026-27", doc_type="book",
            )
        with pytest.raises(ValidationError):
            DocumentUploadMeta(
                department="CSE", semester=9, subject="X",
                academic_year="2026-27", doc_type="book",
            )

    def test_invalid_academic_year(self):
        with pytest.raises(ValidationError):
            DocumentUploadMeta(
                department="CSE", semester=3, subject="X",
                academic_year="2026", doc_type="book",
            )

    def test_invalid_doc_type(self):
        with pytest.raises(ValidationError):
            DocumentUploadMeta(
                department="CSE", semester=3, subject="X",
                academic_year="2026-27", doc_type="homework",
            )

    def test_empty_department_rejected(self):
        with pytest.raises(ValidationError):
            DocumentUploadMeta(
                department="", semester=3, subject="X",
                academic_year="2026-27", doc_type="book",
            )


class TestDocTypeEnum:
    def test_values(self):
        assert set(DocType) == {
            DocType.SYLLABUS, DocType.BOOK, DocType.NOTES, DocType.PREVIOUS_PAPER
        }


class TestIngestionStatusEnum:
    def test_values(self):
        assert set(IngestionStatus) == {
            IngestionStatus.QUEUED, IngestionStatus.PROCESSING,
            IngestionStatus.DONE, IngestionStatus.FAILED,
        }
