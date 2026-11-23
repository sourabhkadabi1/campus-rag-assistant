"""
Stage 7: Practice & Quiz Generation Service.

Generates textbook-grounded Multiple-Choice Questions (MCQs) and
Descriptive Practice Questions with citations, options, and explanations.
Evaluates student quiz submissions with detailed feedback.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.database import execute, fetch, fetchrow
from app.models import (
    PracticeCitation,
    PracticeDifficulty,
    PracticeGenerateRequest,
    PracticeQuestion,
    PracticeQuestionType,
    PracticeSetResponse,
    PracticeSubmitRequest,
    PracticeSubmitResponse,
)
from app.services.llm_router import route_and_generate
from app.services.quota import (
    consume_quota,
    get_user_plan,
    record_tokens,
    refund_quota,
)
from app.services.retrieval import RetrievalResult, hybrid_search

logger = logging.getLogger(__name__)

PRACTICE_UNITS_COST = 2


def _clean_json_text(raw_text: str) -> str:
    """Extract valid JSON from LLM markdown-wrapped response."""
    text = raw_text.strip()
    # Strip markdown code fences ```json ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # If extra text exists before or after the JSON object
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _build_practice_prompt(
    subject: str,
    semester: int,
    department: str,
    chunks: list[RetrievalResult],
    question_type: PracticeQuestionType,
    difficulty: PracticeDifficulty,
    count: int,
    topic: Optional[str] = None,
    chapter_no: Optional[int] = None,
    unit_no: Optional[int] = None,
) -> str:
    """Construct instructions for strictly grounded question generation."""
    context_blocks = []
    for i, c in enumerate(chunks, 1):
        context_blocks.append(
            f"[Source {i}] Document: {c.subject} | Unit: {c.unit_no or 'N/A'} | "
            f"Chapter: {c.chapter_no or 'N/A'} ({c.chapter_title or 'Untitled'}) | "
            f"Pages: {c.page_start}-{c.page_end}\n{c.content}"
        )
    context_text = "\n\n---\n\n".join(context_blocks)

    topic_str = f"Specific Topic / Focus: {topic}\n" if topic else ""
    unit_str = f"Unit: {unit_no}\n" if unit_no is not None else ""
    chapter_str = f"Chapter: {chapter_no}\n" if chapter_no is not None else ""

    prompt = f"""You are an expert college academic examiner creating a rigorous practice quiz for university students.
Generate exactly {count} practice questions grounded STRICTLY in the provided course context excerpts below.

STUDENT & COURSE CONTEXT:
Department: {department} | Semester: {semester} | Subject: {subject}
{topic_str}{unit_str}{chapter_str}Difficulty Level: {difficulty.value.upper()}
Question Type requested: {question_type.value.upper()}

GROUNDING RULES:
1. Every question must test concepts present in the provided course material excerpts below.
2. For MCQ questions:
   - Provide exactly 4 plausible options labeled "A) ...", "B) ...", "C) ...", "D) ...".
   - Provide "correct_option_index" as an integer 0, 1, 2, or 3 corresponding to option A, B, C, or D.
   - Provide "model_answer" explaining concisely why the correct option is right and others are incorrect.
3. For Descriptive questions:
   - Provide a university-level conceptual or analytical question.
   - Provide a complete "model_answer" (1-2 paragraphs).
   - Provide "key_points": a list of 3-5 core points an examiner looks for in full-credit answers.
4. Attach citation details (chapter_no, chapter_title, unit_no, page_start, page_end) matching the source excerpt.
5. Return ONLY a single valid JSON object. No intro, no commentary, no markdown text outside the JSON.

REQUIRED JSON FORMAT:
{{
  "questions": [
    {{
      "id": "q1",
      "type": "mcq",
      "question": "Clear question text here?",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_option_index": 0,
      "model_answer": "Explanation of correct answer.",
      "key_points": ["Key concept 1", "Key concept 2"],
      "citation": {{
        "chapter_no": 1,
        "chapter_title": "Example Chapter",
        "unit_no": 1,
        "page_start": 10,
        "page_end": 12
      }}
    }}
  ]
}}

EXCERPTS FROM COURSE MATERIAL:
{context_text}
"""
    return prompt


async def generate_practice_set(
    user_id: str,
    semester: int,
    department: str,
    req: PracticeGenerateRequest,
    academic_year: str = "2026-27",
) -> PracticeSetResponse:
    """
    Generate a textbook-grounded practice set or quiz for the student.
    Enforces plan feature check, atomic quota deduction, and retrieval.
    """
    # 1. Plan feature check
    plan = await get_user_plan(user_id)
    features = plan.get("features", {})
    if not features.get("quiz_generation", False) and not plan.get("is_paid", False):
        raise ValueError(
            "Quiz and practice question generation is a Premium feature. "
            "Please upgrade to the Premium plan to access interactive quizzes and practice tests."
        )

    # 2. Atomic quota consumption (2 units for practice generation)
    ok, usage = await consume_quota(
        user_id,
        requests_limit=plan["requests_per_day"],
        tokens_limit=plan["tokens_per_day"],
        units=PRACTICE_UNITS_COST,
    )
    if not ok:
        raise ValueError(
            "Daily quota exceeded. You need at least 2 question units to generate a practice set."
        )

    # 3. Retrieve grounding chunks
    retrieval_query = req.topic or f"{req.subject} syllabus concepts practice quiz"
    if req.chapter_no:
        retrieval_query = f"Chapter {req.chapter_no} {retrieval_query}"
    if req.unit_no:
        retrieval_query = f"Unit {req.unit_no} {retrieval_query}"

    chunks, _ = await hybrid_search(
        query=retrieval_query,
        semester=semester,
        department=department,
        subject=req.subject,
        chapter_no=req.chapter_no,
        unit_no=req.unit_no,
        limit=6,
    )

    if not chunks:
        # Refund quota before aborting
        await refund_quota(user_id, units=PRACTICE_UNITS_COST)
        raise ValueError(
            f"No course material found for subject '{req.subject}' (Sem {semester}, {department}). "
            "Please make sure textbooks, syllabus, or lecture slides are uploaded."
        )

    # 4. Generate questions via LLM Router
    prompt = _build_practice_prompt(
        subject=req.subject,
        semester=semester,
        department=department,
        chunks=chunks,
        question_type=req.question_type,
        difficulty=req.difficulty,
        count=req.count,
        topic=req.topic,
        chapter_no=req.chapter_no,
        unit_no=req.unit_no,
    )

    is_paid = plan.get("is_paid", True)
    api_key = settings.gemini_api_key_paid if is_paid else settings.gemini_api_key_free
    if not api_key:
        api_key = settings.gemini_api_key

    generated_text = ""
    input_tokens = 0
    output_tokens = 0
    model_used = "unknown"

    try:
        async for event in route_and_generate(
            chunks=chunks,
            question=prompt,
            history=None,
            detailed=True,
            is_paid=is_paid,
            api_key=api_key,
            max_output_tokens=2000,
        ):
            ev_type = event.get("type")
            if ev_type == "model_selected":
                model_used = event.get("model_id", "unknown")
            elif ev_type == "token":
                generated_text += event.get("text", "")
            elif ev_type == "usage":
                input_tokens = event.get("input_tokens", 0)
                output_tokens = event.get("output_tokens", 0)
            elif ev_type == "error":
                raise RuntimeError(event.get("text", "LLM generation failed"))
    except Exception as exc:
        logger.exception("Practice generation LLM call failed: %s", exc)
        await refund_quota(user_id, units=PRACTICE_UNITS_COST)
        raise RuntimeError(f"Practice generation failed: {exc}")

    # Record token usage
    total_tokens = input_tokens + output_tokens
    if total_tokens > 0:
        await record_tokens(user_id, total_tokens)

    # 5. Parse questions from JSON
    cleaned_json = _clean_json_text(generated_text)
    try:
        data = json.loads(cleaned_json)
        raw_questions = data.get("questions", [])
    except Exception as exc:
        logger.warning("Failed to parse JSON directly (%s). Raw: %s", exc, generated_text[:300])
        # Fallback question structure if model output was malformed
        raw_questions = [
            {
                "id": "q1",
                "type": req.question_type.value if req.question_type != PracticeQuestionType.MIXED else "mcq",
                "question": f"Key principles and core concepts of {req.subject}",
                "options": [
                    f"A) Fundamentals of {req.subject}",
                    f"B) Unrelated principles",
                    f"C) Obsolete methods",
                    f"D) None of the above",
                ],
                "correct_option_index": 0,
                "model_answer": generated_text[:400] if generated_text else "Refer to course notes.",
                "key_points": [req.subject, "Key definitions"],
            }
        ]

    # Validate and standardize questions
    parsed_questions: list[PracticeQuestion] = []
    first_chunk = chunks[0] if chunks else None

    for i, q in enumerate(raw_questions, 1):
        q_id = q.get("id") or f"q{i}"
        q_type = q.get("type", "mcq")
        if req.question_type == PracticeQuestionType.MCQ:
            q_type = "mcq"
        elif req.question_type == PracticeQuestionType.DESCRIPTIVE:
            q_type = "descriptive"

        # Citation fallback to retrieved chunk
        c_dict = q.get("citation") or {}
        citation = PracticeCitation(
            document_id=c_dict.get("document_id") or (first_chunk.document_id if first_chunk else None),
            doc_type=c_dict.get("doc_type") or (first_chunk.doc_type if first_chunk else None),
            chapter_no=c_dict.get("chapter_no") or (first_chunk.chapter_no if first_chunk else None),
            chapter_title=c_dict.get("chapter_title") or (first_chunk.chapter_title if first_chunk else None),
            unit_no=c_dict.get("unit_no") or (first_chunk.unit_no if first_chunk else None),
            page_start=c_dict.get("page_start") or (first_chunk.page_start if first_chunk else None),
            page_end=c_dict.get("page_end") or (first_chunk.page_end if first_chunk else None),
        )

        pq = PracticeQuestion(
            id=q_id,
            type=q_type,
            question=q.get("question", f"Practice Question {i}"),
            options=q.get("options") if q_type == "mcq" else None,
            correct_option_index=q.get("correct_option_index", 0) if q_type == "mcq" else None,
            model_answer=q.get("model_answer", "Review the referenced textbook chapter."),
            key_points=q.get("key_points") or [],
            citation=citation,
        )
        parsed_questions.append(pq)

    # 6. Save in DB
    practice_id = str(uuid.uuid4())
    questions_json = json.dumps([q.model_dump() for q in parsed_questions])

    await execute(
        """INSERT INTO practice_sets
           (id, user_id, subject, semester, department, academic_year,
            topic, unit_no, chapter_no, question_type, difficulty,
            questions, token_usage)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)""",
        practice_id,
        user_id,
        req.subject,
        semester,
        department,
        academic_year,
        req.topic,
        req.unit_no,
        req.chapter_no,
        req.question_type.value,
        req.difficulty.value,
        questions_json,
        total_tokens,
    )

    logger.info(
        "Generated practice set %s for user %s: %d questions (%s) model=%s",
        practice_id,
        user_id,
        len(parsed_questions),
        req.question_type.value,
        model_used,
    )

    return PracticeSetResponse(
        id=practice_id,
        subject=req.subject,
        semester=semester,
        department=department,
        academic_year=academic_year,
        topic=req.topic,
        unit_no=req.unit_no,
        chapter_no=req.chapter_no,
        question_type=req.question_type.value,
        difficulty=req.difficulty.value,
        questions=parsed_questions,
        units_charged=PRACTICE_UNITS_COST,
        created_at=datetime.now(timezone.utc),
    )


async def submit_practice_answers(
    user_id: str,
    req: PracticeSubmitRequest,
) -> PracticeSubmitResponse:
    """Evaluate submitted quiz answers, compute score, and record submission."""
    row = await fetchrow(
        "SELECT id, user_id, questions FROM practice_sets WHERE id = $1",
        req.practice_set_id,
    )
    if not row:
        raise ValueError("Practice set not found")

    questions_raw = row["questions"]
    questions = json.loads(questions_raw) if isinstance(questions_raw, str) else questions_raw

    score = 0
    total_mcqs = 0
    feedback: list[dict] = []

    for q in questions:
        q_id = q.get("id")
        q_type = q.get("type", "mcq")

        if q_type == "mcq":
            total_mcqs += 1
            selected = req.answers.get(q_id)
            correct_idx = q.get("correct_option_index")
            is_correct = (selected is not None) and (selected == correct_idx)

            if is_correct:
                score += 1

            feedback.append({
                "question_id": q_id,
                "type": "mcq",
                "question": q.get("question"),
                "selected_option_index": selected,
                "correct_option_index": correct_idx,
                "is_correct": is_correct,
                "model_answer": q.get("model_answer"),
                "citation": q.get("citation"),
            })
        else:
            # Descriptive self-check feedback
            feedback.append({
                "question_id": q_id,
                "type": "descriptive",
                "question": q.get("question"),
                "model_answer": q.get("model_answer"),
                "key_points": q.get("key_points", []),
                "citation": q.get("citation"),
            })

    total = total_mcqs if total_mcqs > 0 else len(questions)
    percentage = round((score / total * 100.0), 1) if total > 0 else 100.0
    submission_id = str(uuid.uuid4())

    await execute(
        """INSERT INTO practice_submissions
           (id, practice_set_id, user_id, score, total, answers)
           VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
        submission_id,
        req.practice_set_id,
        user_id,
        score,
        total,
        json.dumps(req.answers),
    )

    return PracticeSubmitResponse(
        submission_id=submission_id,
        practice_set_id=req.practice_set_id,
        score=score,
        total=total,
        percentage=percentage,
        feedback=feedback,
    )


async def list_user_practice_sets(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Retrieve practice history for a student."""
    rows = await fetch(
        """SELECT id, subject, semester, department, topic, unit_no,
                  chapter_no, question_type, difficulty, created_at,
                  jsonb_array_length(questions) as question_count
           FROM practice_sets
           WHERE user_id = $1
           ORDER BY created_at DESC
           LIMIT $2 OFFSET $3""",
        user_id,
        limit,
        offset,
    )
    return [dict(r) for r in rows]


async def get_practice_set_by_id(
    practice_set_id: str,
    user_id: str,
) -> Optional[dict]:
    """Fetch a single practice set with its questions."""
    row = await fetchrow(
        """SELECT id, subject, semester, department, academic_year, topic,
                  unit_no, chapter_no, question_type, difficulty, questions,
                  created_at
           FROM practice_sets
           WHERE id = $1 AND user_id = $2""",
        practice_set_id,
        user_id,
    )
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("questions"), str):
        d["questions"] = json.loads(d["questions"])
    return d
