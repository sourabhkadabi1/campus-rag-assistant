"""
Tests for the rule-based query filter parser.

Uses the sync helper (no DB) so tests run without a database.
"""

import pytest

from app.services.filter_parser import (
    ParsedQuery,
    parse_query_sync,
    _clean_query,
)
from app.services.answer_cache import make_cache_key, normalize_question


# ╔════════════════════════════════════════════════════════════════╗
# ║  Chapter / unit / semester extraction                         ║
# ╚════════════════════════════════════════════════════════════════╝


class TestChapterDetection:
    def test_chapter_keyword(self):
        r = parse_query_sync("explain chapter 2 normalization")
        assert r.chapter_no == 2

    def test_chapter_shorthand_ch(self):
        r = parse_query_sync("in ch 3 explain joins")
        assert r.chapter_no == 3

    def test_chapter_shorthand_ch_dot(self):
        r = parse_query_sync("ch.5 ER diagrams")
        assert r.chapter_no == 5

    def test_no_chapter(self):
        r = parse_query_sync("what is a primary key")
        assert r.chapter_no is None


class TestUnitDetection:
    def test_unit_keyword(self):
        r = parse_query_sync("key points of unit 4")
        assert r.unit_no == 4

    def test_module_keyword(self):
        r = parse_query_sync("module 2 summary")
        assert r.unit_no == 2

    def test_no_unit(self):
        r = parse_query_sync("explain normalization")
        assert r.unit_no is None


class TestSemesterDetection:
    def test_sem_short(self):
        r = parse_query_sync("sem 3 chapter 2 normalization")
        assert r.mentioned_semester == 3

    def test_semester_long(self):
        r = parse_query_sync("semester 5 databases")
        assert r.mentioned_semester == 5

    def test_no_semester(self):
        r = parse_query_sync("explain normalization")
        assert r.mentioned_semester is None


# ╔════════════════════════════════════════════════════════════════╗
# ║  Request type detection                                       ║
# ╚════════════════════════════════════════════════════════════════╝


class TestRequestTypeDetection:
    def test_summary_request_summarize(self):
        r = parse_query_sync("summarize chapter 3")
        assert r.is_summary_request is True
        assert r.chapter_no == 3

    def test_summary_request_summary_of(self):
        r = parse_query_sync("summary of chapter 1")
        assert r.is_summary_request is True

    def test_key_concepts_request(self):
        r = parse_query_sync("key points of unit 2")
        assert r.is_key_concepts_request is True
        assert r.unit_no == 2

    def test_important_topics(self):
        r = parse_query_sync("important topics in chapter 4")
        assert r.is_key_concepts_request is True

    def test_syllabus_request(self):
        r = parse_query_sync("syllabus of DBMS")
        assert r.is_syllabus_request is True

    def test_what_is_in_unit(self):
        r = parse_query_sync("what is in unit 2")
        assert r.is_syllabus_request is True
        assert r.unit_no == 2

    def test_topics_covered(self):
        r = parse_query_sync("topics covered in chapter 3")
        assert r.is_syllabus_request is True

    def test_detailed_request(self):
        r = parse_query_sync("explain in detail normalization")
        assert r.is_detailed_request is True

    def test_elaborate_request(self):
        r = parse_query_sync("elaborate on ER diagrams")
        assert r.is_detailed_request is True

    def test_not_summary(self):
        r = parse_query_sync("explain normalization in chapter 2")
        assert r.is_summary_request is False

    def test_no_special_type(self):
        r = parse_query_sync("what is a primary key")
        assert r.is_summary_request is False
        assert r.is_key_concepts_request is False
        assert r.is_syllabus_request is False
        assert r.is_detailed_request is False


# ╔════════════════════════════════════════════════════════════════╗
# ║  Subject matching                                             ║
# ╚════════════════════════════════════════════════════════════════╝


class TestSubjectMatching:
    def test_exact_match(self):
        r = parse_query_sync(
            "explain normalization in DBMS",
            known_subjects=["DBMS", "OS", "Networks"],
        )
        assert r.subject == "DBMS"

    def test_case_insensitive(self):
        r = parse_query_sync(
            "explain normalization in dbms",
            known_subjects=["DBMS", "OS"],
        )
        assert r.subject == "DBMS"

    def test_no_match(self):
        r = parse_query_sync(
            "explain normalization",
            known_subjects=["DBMS", "OS"],
        )
        assert r.subject is None

    def test_longer_subject_preferred(self):
        """If both 'OS' and 'Operating Systems' match, pick the longer one."""
        r = parse_query_sync(
            "explain scheduling in Operating Systems",
            known_subjects=["OS", "Operating Systems"],
        )
        assert r.subject == "Operating Systems"

    def test_no_subjects_provided(self):
        r = parse_query_sync("explain normalization in DBMS")
        assert r.subject is None


# ╔════════════════════════════════════════════════════════════════╗
# ║  Clean query                                                  ║
# ╚════════════════════════════════════════════════════════════════╝


class TestCleanQuery:
    def test_strips_semester(self):
        r = parse_query_sync("in sem 3 chapter 2 explain normalization")
        assert "sem 3" not in r.clean_query
        assert "normalization" in r.clean_query

    def test_strips_chapter(self):
        r = parse_query_sync("chapter 2 normalization")
        assert "chapter 2" not in r.clean_query
        assert "normalization" in r.clean_query

    def test_strips_unit(self):
        r = parse_query_sync("unit 4 key concepts")
        assert "unit 4" not in r.clean_query

    def test_preserves_meaningful_words(self):
        r = parse_query_sync(
            "in sem 3 chapter 2 explain normalization in DBMS"
        )
        assert "normalization" in r.clean_query
        assert "DBMS" in r.clean_query

    def test_collapses_whitespace(self):
        r = parse_query_sync("explain   chapter 5   joins")
        assert "  " not in r.clean_query


# ╔════════════════════════════════════════════════════════════════╗
# ║  Combined / integration                                      ║
# ╚════════════════════════════════════════════════════════════════╝


class TestCombinedFilters:
    def test_full_query(self):
        r = parse_query_sync(
            "in sem 3 chapter 2 explain normalization in DBMS",
            known_subjects=["DBMS", "OS"],
        )
        assert r.mentioned_semester == 3
        assert r.chapter_no == 2
        assert r.subject == "DBMS"
        assert "normalization" in r.clean_query
        assert r.is_summary_request is False

    def test_summary_with_subject(self):
        r = parse_query_sync(
            "summarize chapter 3 of DBMS",
            known_subjects=["DBMS"],
        )
        assert r.is_summary_request is True
        assert r.chapter_no == 3
        assert r.subject == "DBMS"


# ╔════════════════════════════════════════════════════════════════╗
# ║  Cache key generation                                         ║
# ╚════════════════════════════════════════════════════════════════╝


class TestCacheKey:
    def test_deterministic(self):
        k1 = make_cache_key("explain normalization", "DBMS", 3)
        k2 = make_cache_key("explain normalization", "DBMS", 3)
        assert k1 == k2

    def test_case_insensitive(self):
        k1 = make_cache_key("EXPLAIN Normalization", "DBMS", 3)
        k2 = make_cache_key("explain normalization", "DBMS", 3)
        assert k1 == k2

    def test_different_semester(self):
        k1 = make_cache_key("explain normalization", "DBMS", 3)
        k2 = make_cache_key("explain normalization", "DBMS", 5)
        assert k1 != k2

    def test_different_subject(self):
        k1 = make_cache_key("explain normalization", "DBMS", 3)
        k2 = make_cache_key("explain normalization", "OS", 3)
        assert k1 != k2

    def test_none_subject(self):
        k1 = make_cache_key("explain normalization", None, 3)
        k2 = make_cache_key("explain normalization", None, 3)
        assert k1 == k2

    def test_with_academic_year(self):
        k1 = make_cache_key("explain normalization", "DBMS", 3, "2026-27")
        k2 = make_cache_key("explain normalization", "DBMS", 3, "2025-26")
        assert k1 != k2

    def test_is_sha256_hex(self):
        key = make_cache_key("test", "DBMS", 3)
        assert len(key) == 64  # SHA-256 hex digest length
        assert all(c in "0123456789abcdef" for c in key)
