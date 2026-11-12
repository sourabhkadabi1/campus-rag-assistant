"""
Chat session management — create, list, get messages, add messages.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.database import execute, fetch, fetchrow, fetchval

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request / response models ────────────────────────────────────


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None


class AddMessageRequest(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., min_length=1)
    citations: Optional[list[dict]] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None


# ── Endpoints ─────────────────────────────────────────────────────


@router.post("/sessions")
async def create_session(request: Request, body: CreateSessionRequest):
    """Create a new chat session."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    session_id = str(uuid.uuid4())
    await execute(
        """INSERT INTO chat_sessions (id, user_id, title, subject)
           VALUES ($1, $2, $3, $4)""",
        session_id, user_id, body.title, body.subject,
    )
    return {"id": session_id, "title": body.title, "subject": body.subject}


@router.get("/sessions")
async def list_sessions(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List chat sessions for the current user, newest first."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header")

    rows = await fetch(
        """SELECT id, title, subject, created_at, updated_at
           FROM chat_sessions
           WHERE user_id = $1
           ORDER BY updated_at DESC
           LIMIT $2 OFFSET $3""",
        user_id, limit, offset,
    )
    total = await fetchval(
        "SELECT count(*) FROM chat_sessions WHERE user_id = $1", user_id
    )
    return {"total": total, "sessions": [dict(r) for r in rows]}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a single chat session."""
    row = await fetchrow(
        "SELECT * FROM chat_sessions WHERE id = $1", session_id
    )
    if not row:
        raise HTTPException(404, "Session not found")
    return dict(row)


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get messages for a chat session, oldest first."""
    session = await fetchrow(
        "SELECT id FROM chat_sessions WHERE id = $1", session_id
    )
    if not session:
        raise HTTPException(404, "Session not found")

    rows = await fetch(
        """SELECT id, role, content, citations, model_used,
                  tokens_used, created_at
           FROM chat_messages
           WHERE session_id = $1
           ORDER BY created_at ASC
           LIMIT $2 OFFSET $3""",
        session_id, limit, offset,
    )

    messages = []
    for r in rows:
        msg = dict(r)
        if isinstance(msg.get("citations"), str):
            msg["citations"] = json.loads(msg["citations"])
        messages.append(msg)

    total = await fetchval(
        "SELECT count(*) FROM chat_messages WHERE session_id = $1",
        session_id,
    )
    return {"session_id": session_id, "total": total, "messages": messages}


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, body: AddMessageRequest):
    """Add a message to a chat session."""
    session = await fetchrow(
        "SELECT id FROM chat_sessions WHERE id = $1", session_id
    )
    if not session:
        raise HTTPException(404, "Session not found")

    msg_id = str(uuid.uuid4())
    citations_json = (
        json.dumps(body.citations) if body.citations else None
    )

    await execute(
        """INSERT INTO chat_messages
           (id, session_id, role, content, citations, model_used, tokens_used)
           VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)""",
        msg_id, session_id, body.role, body.content,
        citations_json, body.model_used, body.tokens_used,
    )

    # Touch session updated_at
    await execute(
        "UPDATE chat_sessions SET updated_at = NOW() WHERE id = $1",
        session_id,
    )

    return {"id": msg_id, "role": body.role}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session and all its messages (cascaded by FK)."""
    result = await execute(
        "DELETE FROM chat_sessions WHERE id = $1", session_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Session not found")
    return {"id": session_id, "deleted": True}
