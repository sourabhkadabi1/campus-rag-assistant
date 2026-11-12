"""
Hybrid search: pgvector cosine similarity + Postgres full-text BM25.
Reciprocal rank fusion to merge results.

If chapter-filtered search returns nothing relevant, retries across the
whole semester and tells the student where the answer was actually found.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.database import fetch
from app.services.embeddings import get_embedding

logger = logging.getLogger(__name__)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Data class                                                   ║
# ╚════════════════════════════════════════════════════════════════╝


@dataclass
class RetrievalResult:
    """A single retrieved chunk with its relevance score."""
    chunk_id: str
    content: str
    score: float
    chapter_no: Optional[int]
    chapter_title: Optional[str]
    unit_no: Optional[int]
    page_start: int
    page_end: int
    subject: str
    doc_type: str
    document_id: str
    search_type: str  # 'vector', 'fulltext', 'fused'


# ╔════════════════════════════════════════════════════════════════╗
# ║  Reciprocal Rank Fusion                                       ║
# ╚════════════════════════════════════════════════════════════════╝

RRF_K = 60  # standard constant


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """
    Merge multiple ranked lists using reciprocal rank fusion.

    Each list: ``[(chunk_id, score), ...]`` in descending score order.
    Returns merged list sorted by fused score descending.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (chunk_id, _) in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Vector search                                                ║
# ╚════════════════════════════════════════════════════════════════╝


async def _vector_search(
    query_embedding: list[float],
    semester: int,
    department: str,
    subject: Optional[str] = None,
    chapter_no: Optional[int] = None,
    chapters: Optional[list[int]] = None,
    academic_year: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Cosine similarity search via pgvector."""
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    conditions = ["d.is_active = TRUE", "c.semester = $1", "c.department = $2"]
    args: list = [semester, department]
    idx = 3

    if subject:
        conditions.append(f"c.subject = ${idx}")
        args.append(subject)
        idx += 1

    if chapter_no is not None:
        conditions.append(f"c.chapter_no = ${idx}")
        args.append(chapter_no)
        idx += 1
    elif chapters:
        conditions.append(f"c.chapter_no = ANY(${idx}::int[])")
        args.append(chapters)
        idx += 1

    if academic_year:
        conditions.append(f"c.academic_year = ${idx}")
        args.append(academic_year)
        idx += 1

    where = " AND ".join(conditions)

    query = f"""
        SELECT c.id, c.content, c.chapter_no, c.chapter_title, c.unit_no,
               c.page_start, c.page_end, c.subject, c.doc_type, c.document_id,
               1 - (c.embedding <=> ${idx}::vector) AS similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE {where}
        ORDER BY c.embedding <=> ${idx}::vector
        LIMIT ${idx + 1}
    """
    args.extend([emb_str, limit])

    return [dict(r) for r in await fetch(query, *args)]


# ╔════════════════════════════════════════════════════════════════╗
# ║  Full-text search                                             ║
# ╚════════════════════════════════════════════════════════════════╝


async def _fulltext_search(
    query_text: str,
    semester: int,
    department: str,
    subject: Optional[str] = None,
    chapter_no: Optional[int] = None,
    chapters: Optional[list[int]] = None,
    academic_year: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Full-text search using tsvector + plainto_tsquery."""
    conditions = ["d.is_active = TRUE", "c.semester = $1", "c.department = $2"]
    args: list = [semester, department]
    idx = 3

    # FTS condition
    conditions.append(
        f"c.search_vector @@ plainto_tsquery('english', ${idx})"
    )
    args.append(query_text)
    idx += 1

    if subject:
        conditions.append(f"c.subject = ${idx}")
        args.append(subject)
        idx += 1

    if chapter_no is not None:
        conditions.append(f"c.chapter_no = ${idx}")
        args.append(chapter_no)
        idx += 1
    elif chapters:
        conditions.append(f"c.chapter_no = ANY(${idx}::int[])")
        args.append(chapters)
        idx += 1

    if academic_year:
        conditions.append(f"c.academic_year = ${idx}")
        args.append(academic_year)
        idx += 1

    where = " AND ".join(conditions)

    query = f"""
        SELECT c.id, c.content, c.chapter_no, c.chapter_title, c.unit_no,
               c.page_start, c.page_end, c.subject, c.doc_type, c.document_id,
               ts_rank(c.search_vector,
                       plainto_tsquery('english', $3)) AS rank
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE {where}
        ORDER BY rank DESC
        LIMIT ${idx}
    """
    args.append(limit)

    return [dict(r) for r in await fetch(query, *args)]


# ╔════════════════════════════════════════════════════════════════╗
# ║  Public: hybrid_search                                        ║
# ╚════════════════════════════════════════════════════════════════╝


async def hybrid_search(
    query: str,
    semester: int,
    department: str,
    subject: Optional[str] = None,
    chapter_no: Optional[int] = None,
    unit_chapters: Optional[list[int]] = None,
    academic_year: Optional[str] = None,
    limit: int = 4,
) -> tuple[list[RetrievalResult], Optional[str]]:
    """
    Perform hybrid vector + full-text search with reciprocal rank fusion.

    Returns ``(results, fallback_message)``.
    *fallback_message* is set when chapter-filtered search found nothing
    and we retried across the whole semester.
    """
    # 1. Embed the query
    query_embedding = get_embedding(query)

    # 2. Determine chapter filter
    chapters = None
    if chapter_no is None and unit_chapters:
        chapters = unit_chapters

    # 3. Filtered search
    vec_results = await _vector_search(
        query_embedding, semester, department,
        subject=subject, chapter_no=chapter_no, chapters=chapters,
        academic_year=academic_year, limit=limit * 3,
    )
    ft_results = await _fulltext_search(
        query, semester, department,
        subject=subject, chapter_no=chapter_no, chapters=chapters,
        academic_year=academic_year, limit=limit * 3,
    )

    fallback_message: Optional[str] = None

    # 4. Chapter fallback — retry across whole semester if nothing found
    if (
        not vec_results
        and not ft_results
        and (chapter_no or chapters or subject)
    ):
        logger.info("Filtered search empty — retrying across whole semester")
        vec_results = await _vector_search(
            query_embedding, semester, department,
            academic_year=academic_year, limit=limit * 3,
        )
        ft_results = await _fulltext_search(
            query, semester, department,
            academic_year=academic_year, limit=limit * 3,
        )

        if vec_results or ft_results:
            # Build a helpful fallback message
            parts = []
            if chapter_no:
                parts.append(f"not in Chapter {chapter_no}")
            elif subject:
                parts.append(f"not in {subject}")

            found_chapters: set[int] = set()
            for r in vec_results + ft_results:
                if r.get("chapter_no"):
                    found_chapters.add(r["chapter_no"])

            if found_chapters:
                ch_str = ", ".join(
                    f"Chapter {c}" for c in sorted(found_chapters)[:3]
                )
                parts.append(f"found in {ch_str}")

            fallback_message = ", ".join(parts) if parts else None

    # 5. Reciprocal rank fusion
    vec_ranked = [(str(r["id"]), r.get("similarity", 0)) for r in vec_results]
    ft_ranked = [(str(r["id"]), r.get("rank", 0)) for r in ft_results]
    fused = reciprocal_rank_fusion([vec_ranked, ft_ranked])

    # 6. Build result list
    all_results = {str(r["id"]): r for r in vec_results + ft_results}

    results: list[RetrievalResult] = []
    for chunk_id, fused_score in fused[:limit]:
        r = all_results[chunk_id]
        results.append(RetrievalResult(
            chunk_id=chunk_id,
            content=r["content"],
            score=fused_score,
            chapter_no=r.get("chapter_no"),
            chapter_title=r.get("chapter_title"),
            unit_no=r.get("unit_no"),
            page_start=r.get("page_start", 0),
            page_end=r.get("page_end", 0),
            subject=r.get("subject", ""),
            doc_type=r.get("doc_type", ""),
            document_id=str(r.get("document_id", "")),
            search_type="fused",
        ))

    return results, fallback_message
