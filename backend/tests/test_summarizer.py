"""
Tests for the summarizer's pure helper functions.
No API calls — only tests _parse_key_concepts.
"""

from __future__ import annotations

from app.services.summarizer import _parse_key_concepts


class TestParseKeyConcepts:
    def test_standard_format(self):
        text = """\
## Summary
Some summary text here.

## Key Concepts
- Normalisation: Process of organising data
- BCNF: Boyce-Codd Normal Form
- Functional Dependency: A constraint between attributes
"""
        concepts = _parse_key_concepts(text)
        assert len(concepts) == 3
        assert "Normalisation: Process of organising data" in concepts
        assert "BCNF: Boyce-Codd Normal Form" in concepts

    def test_stops_at_next_section(self):
        text = """\
## Key Concepts
- First concept
- Second concept

## Examples
- Not a concept
"""
        concepts = _parse_key_concepts(text)
        assert len(concepts) == 2
        assert "Not a concept" not in concepts

    def test_no_concepts_section(self):
        text = "Just a plain summary without any structured sections."
        concepts = _parse_key_concepts(text)
        assert concepts == []

    def test_empty_text(self):
        assert _parse_key_concepts("") == []

    def test_case_insensitive_header(self):
        text = """\
## KEY CONCEPTS
- Concept one
- Concept two
"""
        # Our parser looks for "key concept" in lower, so "KEY CONCEPTS" should work
        concepts = _parse_key_concepts(text)
        assert len(concepts) == 2
