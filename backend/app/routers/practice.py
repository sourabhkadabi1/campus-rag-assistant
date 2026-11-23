"""
Stage 7: Practice & Quiz Router.

Endpoints for generating semester/subject-grounded quizzes, submitting answers,
scoring, and viewing practice history.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import (
    PracticeGenerateRequest,
    PracticeSetResponse,
    PracticeSubmitRequest,
    PracticeSubmitResponse,
)
from app.services.practice_generator import (
    generate_practice_set,
    get_practice_set_by_id,
    list_user_practice_sets,
    submit_practice_answers,
)
from app.services.security import get_server_profile, sanitize_text_input, validate_metadata_field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/practice", tags=["practice"])


@router.post("/generate", response_model=PracticeSetResponse)
async def generate_quiz(request: Request, body: PracticeGenerateRequest):
    """
    Generate an interactive practice set or quiz grounded in course textbooks.

    Requires:
      - X-User-Id header
      - Premium plan with quiz_generation feature flag enabled
      - Consumes 2 question units atomically
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    # 1. Resolve student identity & semester/department
    profile = await get_server_profile(user_id)
    if profile:
        semester = int(profile.get("semester") or 3)
        department = str(profile.get("department") or "CSE")
    else:
        # Fallback to request headers
        try:
            semester = int(request.headers.get("X-Semester", 3))
        except (ValueError, TypeError):
            semester = 3
        department = request.headers.get("X-Department", "CSE")

    # 2. Sanitize inputs
    body.subject = validate_metadata_field(body.subject, "subject")
    if body.topic:
        body.topic = sanitize_text_input(body.topic, max_length=150)

    try:
        result = await generate_practice_set(
            user_id=user_id,
            semester=semester,
            department=department,
            req=body,
        )
        return result
    except ValueError as val_err:
        err_msg = str(val_err)
        if "Premium" in err_msg:
            raise HTTPException(403, detail=err_msg)
        elif "quota" in err_msg.lower():
            raise HTTPException(429, detail=err_msg)
        elif "No course material" in err_msg:
            raise HTTPException(404, detail=err_msg)
        raise HTTPException(400, detail=err_msg)
    except Exception as exc:
        logger.exception("Error in /practice/generate: %s", exc)
        raise HTTPException(500, detail=f"Failed to generate practice quiz: {exc}")


@router.post("/submit", response_model=PracticeSubmitResponse)
async def submit_quiz(request: Request, body: PracticeSubmitRequest):
    """
    Submit completed quiz answers for evaluation and score calculation.
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    try:
        response = await submit_practice_answers(user_id=user_id, req=body)
        return response
    except ValueError as val_err:
        raise HTTPException(404, detail=str(val_err))
    except Exception as exc:
        logger.exception("Error in /practice/submit: %s", exc)
        raise HTTPException(500, detail=f"Failed to evaluate submission: {exc}")


@router.get("/history")
async def get_practice_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List past practice sets for the authenticated student.
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    items = await list_user_practice_sets(user_id=user_id, limit=limit, offset=offset)
    return {"total": len(items), "items": items}


@router.get("/{practice_set_id}")
async def get_practice_quiz(request: Request, practice_set_id: str):
    """
    Retrieve a specific practice set with questions.
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    quiz = await get_practice_set_by_id(practice_set_id=practice_set_id, user_id=user_id)
    if not quiz:
        raise HTTPException(404, detail="Practice set not found")
    return quiz
