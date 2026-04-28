"""
Call Summarizer endpoints.

POST /workspaces/{id}/calls/upload
  — Accepts multipart audio file, creates CallSummary row, enqueues Whisper task.
  — Returns call_summary_id + job_id immediately (async processing).

GET  /workspaces/{id}/calls
  — Lists all call summaries for workspace, newest first.

GET  /workspaces/{id}/calls/{call_id}
  — Full detail: transcript, summary, action items.

DELETE /workspaces/{id}/calls/{call_id}
  — Remove a call summary.
"""
from __future__ import annotations

import os
import tempfile
import uuid as uuid_mod
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.call_summary import CallSummary
from app.models.user import User

router = APIRouter()

ALLOWED_AUDIO = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".webm", ".flac"}
MAX_UPLOAD_MB = int(os.getenv("MAX_CALL_UPLOAD_MB", "50"))


@router.post("/workspaces/{workspace_id}/calls/upload", status_code=202)
async def upload_call(
    workspace_id: uuid_mod.UUID,
    file: UploadFile = File(...),
    title: str = Form(default="Untitled Call"),
    contact_id: str | None = Form(default=None),
    participants: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    suffix = Path(file.filename or "audio.mp3").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported audio format '{suffix}'. Allowed: {', '.join(ALLOWED_AUDIO)}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_MB} MB limit",
        )

    # Save to temp file (Whisper needs a path, not a buffer)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.flush()
    tmp.close()

    contact_uuid: uuid_mod.UUID | None = None
    if contact_id:
        try:
            contact_uuid = uuid_mod.UUID(contact_id)
        except ValueError:
            pass

    call = CallSummary(
        workspace_id=workspace_id,
        contact_id=contact_uuid,
        title=title,
        participants=participants,
        transcript="",
        summary="",
        action_items=[],
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    from app.workers.transcribe import transcribe_call
    task = transcribe_call.delay(str(call.id), tmp.name)

    return {"call_summary_id": str(call.id), "job_id": task.id, "status": "processing"}


@router.get("/workspaces/{workspace_id}/calls")
async def list_calls(
    workspace_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from sqlalchemy import desc

    result = await db.execute(
        select(CallSummary)
        .where(CallSummary.workspace_id == workspace_id)
        .order_by(desc(CallSummary.call_date))
        .limit(50)
    )
    calls = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "contact_id": str(c.contact_id) if c.contact_id else None,
            "title": c.title,
            "duration_seconds": c.duration_seconds,
            "summary": c.summary,
            "action_items": c.action_items,
            "participants": c.participants,
            "call_date": c.call_date.isoformat(),
            "processing": not c.transcript,
        }
        for c in calls
    ]


@router.get("/workspaces/{workspace_id}/calls/{call_id}")
async def get_call(
    workspace_id: uuid_mod.UUID,
    call_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(CallSummary).where(
            CallSummary.id == call_id,
            CallSummary.workspace_id == workspace_id,
        )
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    return {
        "id": str(call.id),
        "contact_id": str(call.contact_id) if call.contact_id else None,
        "title": call.title,
        "duration_seconds": call.duration_seconds,
        "transcript": call.transcript,
        "summary": call.summary,
        "action_items": call.action_items,
        "participants": call.participants,
        "call_date": call.call_date.isoformat(),
        "model_used": call.model_used,
        "processing": not call.transcript,
    }


@router.delete("/workspaces/{workspace_id}/calls/{call_id}")
async def delete_call(
    workspace_id: uuid_mod.UUID,
    call_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(CallSummary).where(
            CallSummary.id == call_id,
            CallSummary.workspace_id == workspace_id,
        )
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    await db.delete(call)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
