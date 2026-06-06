"""
Webhook delivery log router.

Endpoints:
  GET /workspaces/{id}/webhook-logs — paginated list with optional source/status filters
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.webhook_log import WebhookLog

router = APIRouter()


@router.get("/workspaces/{workspace_id}/webhook-logs")
async def list_webhook_logs(
    workspace_id: UUID,
    source: str | None = Query(default=None, description="Filter by source: gmail | slack"),
    log_status: str | None = Query(default=None, alias="status", description="Filter by status: received | queued | error"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return webhook delivery log entries for the workspace, newest first."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = (
        select(WebhookLog)
        .where(WebhookLog.workspace_id == workspace_id)
        .order_by(desc(WebhookLog.created_at))
        .limit(limit)
        .offset(offset)
    )
    if source:
        q = q.where(WebhookLog.source == source)
    if log_status:
        q = q.where(WebhookLog.status == log_status)

    result = await db.execute(q)
    logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "workspace_id": str(log.workspace_id) if log.workspace_id else None,
            "source": log.source,
            "event_type": log.event_type,
            "status": log.status,
            "payload_summary": log.payload_summary,
            "job_id": log.job_id,
            "error_detail": log.error_detail,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
