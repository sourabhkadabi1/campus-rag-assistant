"""
Rule-based query filter extraction — NO LLM calls.

Parses semester, chapter, unit, subject references from student questions.
Maps unit → chapters via unit_chapter_map table.
Output: {subject, chapter, unit, clean_query, request_type}.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.database import fetch

# ╔════════════════════════════════════════════════════════════════╗
# ║  Result dataclass                                             ║
# ╚════════════════════════════════════════════════════════════════╝


@dataclass
class ParsedQuery:
    """Result of filter parsing."""
    clean_query: str                        # question with filter tokens removed
    subject: Optional[str] = None           # detected subject name
    chapter_no: Optional[int] = None        # detected chapter number
    unit_no: Optional[int] = None           # detected unit number
    mentioned_semester: Optional[int] = None  # semester mentioned (for validation)
    is_summary_request: bool = False        # "summarize chapter X"
    is_key_concepts_request: bool = False   # "key points of unit Y"
    is_syllabus_request: bool = False       # "syllabus of ..."
    is_detailed_request: bool = False       # "explain in detail"
    matched_chapters_from_unit: list[int] = field(default_factory=list)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Regex patterns                                               ║
# ╚════════════════════════════════════════════════════════════════╝

CHAPTER_PATTERNS = [
    re.compile(r"\bchapter\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\bch\.?\s*(\d+)\b", re.IGNORECASE),
]

UNIT_PATTERNS = [
    re.compile(r"\bunit\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\bmodule\s+(\d+)\b", re.IGNORECASE),
]

SEMESTER_PATTERNS = [
    re.compile(r"\bsem(?:ester)?\s+(\d+)\b", re.IGNORECASE),
]

SUMMARY_PATTERNS = [
    re.compile(r"\b(?:summarize|summarise|summary\s+of)\b", re.IGNORECASE),
    re.compile(r"\bsummar(?:y|ize|ise)\b", re.IGNORECASE),
]

KEY_CONCEPTS_PATTERNS = [
    re.compile(r"\bkey\s+(?:points?|concepts?|topics?)\b", re.IGNORECASE),
    re.compile(r"\bimportant\s+(?:points?|concepts?|topics?)\b", re.IGNORECASE),
]

SYLLABUS_PATTERNS = [
    re.compile(r"\bsyllabus\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+is\s+in\s+unit\b", re.IGNORECASE),
    re.compile(r"\btopics?\s+(?:in|of|covered)\b", re.IGNORECASE),
]

DETAILED_PATTERNS = [
    re.compile(r"\b(?:in\s+)?detail(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bexplain\s+(?:in\s+)?detail\b", re.IGNORECASE),
    re.compile(r"\belaborate\b", re.IGNORECASE),
]

# Tokens to strip from the clean query
FILTER_STRIP_PATTERNS = [
    re.compile(r"\bsem(?:ester)?\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bchapter\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bch\.?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bunit\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bmodule\s+\d+\b", re.IGNORECASE),
]


# ╔════════════════════════════════════════════════════════════════╗
# ║  Extraction helpers                                           ║
# ╚════════════════════════════════════════════════════════════════╝


def _extract_int(patterns: list[re.Pattern], text: str) -> Optional[int]:
    """Extract the first integer match from a list of patterns."""
    for pat in patterns:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def _check_any(patterns: list[re.Pattern], text: str) -> bool:
    """True if any pattern matches the text."""
    return any(p.search(text) for p in patterns)


def _clean_query(text: str) -> str:
    """Remove filter tokens from the query, collapse whitespace."""
    result = text
    for pat in FILTER_STRIP_PATTERNS:
        result = pat.sub("", result)
    # Collapse whitespace and strip
    result = re.sub(r"\s+", " ", result).strip()
    # Remove dangling prepositions left at start
    result = re.sub(r"^(?:in|of|from|about)\s+", "", result, flags=re.IGNORECASE)
    # Remove dangling prepositions left at end
    result = re.sub(r"\s+(?:in|of|from|about)$", "", result, flags=re.IGNORECASE)
    return result.strip()


def _match_subject(
    text: str, known_subjects: list[str]
) -> Optional[str]:
    """Match a subject name or common alias in the text."""
    text_lower = text.lower()
    # Sort by length descending so longer names match first
    for subj in sorted(known_subjects, key=len, reverse=True):
        pattern = re.compile(r"\b" + re.escape(subj.lower()) + r"\b")
        if pattern.search(text_lower):
            return subj
    return None


# ╔════════════════════════════════════════════════════════════════╗
# ║  DB lookups (async)                                           ║
# ╚════════════════════════════════════════════════════════════════╝


async def get_known_subjects(semester: int, department: str) -> list[str]:
    """Fetch distinct subject names from active documents."""
    rows = await fetch(
        """SELECT DISTINCT subject FROM documents
           WHERE semester = $1 AND department = $2 AND is_active = TRUE""",
        semester, department,
    )
    return [r["subject"] for r in rows]


async def get_unit_chapter_mapping(
    subject: str, semester: int, department: str
) -> dict[int, list[int]]:
    """Fetch unit → chapters mapping. Returns {unit_no: [chapter_nos]}."""
    rows = await fetch(
        """SELECT unit_no, chapter_no FROM unit_chapter_map
           WHERE subject = $1 AND semester = $2 AND department = $3
           ORDER BY unit_no, chapter_no""",
        subject, semester, department,
    )
    mapping: dict[int, list[int]] = {}
    for r in rows:
        mapping.setdefault(r["unit_no"], []).append(r["chapter_no"])
    return mapping


# ╔════════════════════════════════════════════════════════════════╗
# ║  Main parser (async — uses DB)                                ║
# ╚════════════════════════════════════════════════════════════════╝


async def parse_query(
    question: str,
    semester: int,
    department: str,
) -> ParsedQuery:
    """
    Parse a student question into structured filters.

    Semester and department come from the authenticated profile
    (never trusted from the request body).
    """
    result = ParsedQuery(clean_query=question)

    # 1. Extract mentioned semester (for validation, not filtering)
    result.mentioned_semester = _extract_int(SEMESTER_PATTERNS, question)

    # 2. Extract chapter and unit
    result.chapter_no = _extract_int(CHAPTER_PATTERNS, question)
    result.unit_no = _extract_int(UNIT_PATTERNS, question)

    # 3. Detect request types
    result.is_summary_request = _check_any(SUMMARY_PATTERNS, question)
    result.is_key_concepts_request = _check_any(KEY_CONCEPTS_PATTERNS, question)
    result.is_syllabus_request = _check_any(SYLLABUS_PATTERNS, question)
    result.is_detailed_request = _check_any(DETAILED_PATTERNS, question)

    # 4. Match subject against known subjects from DB
    try:
        subjects = await get_known_subjects(semester, department)
        result.subject = _match_subject(question, subjects)
    except Exception:
        pass  # DB unavailable — subject matching skipped

    # 5. Map unit → chapters via unit_chapter_map
    if result.unit_no:
        subject_for_map = result.subject
        if subject_for_map:
            try:
                mapping = await get_unit_chapter_mapping(
                    subject_for_map, semester, department
                )
                result.matched_chapters_from_unit = mapping.get(
                    result.unit_no, []
                )
            except Exception:
                pass

    # 6. Clean query (strip filter tokens)
    result.clean_query = _clean_query(question)

    return result


# ╔════════════════════════════════════════════════════════════════╗
# ║  Sync helper (for unit tests without a DB)                    ║
# ╚════════════════════════════════════════════════════════════════╝


def parse_query_sync(
    question: str,
    known_subjects: list[str] | None = None,
) -> ParsedQuery:
    """
    Synchronous parse — no DB calls.
    Only extracts chapter, unit, semester, request types, and optional subject.
    """
    result = ParsedQuery(clean_query=question)
    result.mentioned_semester = _extract_int(SEMESTER_PATTERNS, question)
    result.chapter_no = _extract_int(CHAPTER_PATTERNS, question)
    result.unit_no = _extract_int(UNIT_PATTERNS, question)
    result.is_summary_request = _check_any(SUMMARY_PATTERNS, question)
    result.is_key_concepts_request = _check_any(KEY_CONCEPTS_PATTERNS, question)
    result.is_syllabus_request = _check_any(SYLLABUS_PATTERNS, question)
    result.is_detailed_request = _check_any(DETAILED_PATTERNS, question)
    if known_subjects:
        result.subject = _match_subject(question, known_subjects)
    result.clean_query = _clean_query(question)
    return result
