"""
Semantic search endpoints.

GET  /workspaces/{id}/contacts/search?q=<text>&limit=<n>
  — Returns contacts ranked by cosine similarity to query embedding.
  — Falls back to ILIKE name/company search if no embeddings exist yet.

GET  /workspaces/{id}/search?q=<text>&limit=<n>
  — Global search across contacts, deals, and tasks simultaneously.

POST /workspaces/{id}/contacts/embed
  — Enqueues a Celery task to embed all workspace contacts.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.task import Task
from app.models.user import User

router = APIRouter()


@router.get("/workspaces/{workspace_id}/contacts/search")
async def semantic_search(
    workspace_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.services.embedding import embed_text

    query_vec = embed_text(q)

    # Check if any contacts have embeddings
    count_result = await db.execute(
        text(
            "SELECT COUNT(*) FROM contacts "
            "WHERE workspace_id = :wid AND embedding IS NOT NULL"
        ),
        {"wid": str(workspace_id)},
    )
    embedded_count: int = count_result.scalar() or 0

    if embedded_count > 0:
        # Vector similarity search using pgvector cosine distance (<=>)
        rows = await db.execute(
            text(
                "SELECT id, name, email, company, role, status, ml_score, revenue, deal_count, "
                "       1 - (embedding <=> CAST(:vec AS vector)) AS score "
                "FROM contacts "
                "WHERE workspace_id = :wid AND embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(:vec AS vector) "
                "LIMIT :lim"
            ),
            {"vec": str(query_vec), "wid": str(workspace_id), "lim": limit},
        )
        results = rows.mappings().all()
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "email": r["email"],
                "company": r["company"],
                "role": r["role"],
                "status": r["status"],
                "ml_score": r["ml_score"],
                "revenue": float(r["revenue"] or 0),
                "deal_count": r["deal_count"] or 0,
                "similarity": round(float(r["score"]), 4),
            }
            for r in results
        ]
    else:
        # Fallback: substring match on name / company / email
        result = await db.execute(
            select(Contact)
            .where(
                Contact.workspace_id == workspace_id,
                (
                    func.lower(Contact.name).contains(q.lower())
                    | func.lower(Contact.company).contains(q.lower())
                    | func.lower(Contact.email).contains(q.lower())
                ),
            )
            .limit(limit)
        )
        contacts = result.scalars().all()
        return [
            {
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "company": c.company,
                "role": c.role,
                "status": c.status,
                "ml_score": c.ml_score,
                "revenue": float(c.revenue or 0),
                "deal_count": c.deal_count or 0,
                "similarity": None,
            }
            for c in contacts
        ]


@router.post("/workspaces/{workspace_id}/contacts/embed", status_code=202)
async def trigger_embed(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enqueue a Celery job to embed all contacts in this workspace."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.workers.embed_contacts import embed_workspace_contacts
    from app.routers.agents import _mark_job_dispatched

    task = embed_workspace_contacts.delay(str(workspace_id))
    _mark_job_dispatched(task.id, str(workspace_id))
    return {"job_id": task.id, "status": "queued"}


@router.get("/workspaces/{workspace_id}/search")
async def global_search(
    workspace_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Search contacts, deals, and tasks in a single request."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q_lower = q.lower()

    contact_result = await db.execute(
        select(Contact)
        .where(
            Contact.workspace_id == workspace_id,
            (
                func.lower(Contact.name).contains(q_lower)
                | func.lower(Contact.company).contains(q_lower)
                | func.lower(Contact.email).contains(q_lower)
            ),
        )
        .limit(limit)
    )
    contacts = contact_result.scalars().all()

    deal_result = await db.execute(
        select(Deal)
        .where(
            Deal.workspace_id == workspace_id,
            (
                func.lower(Deal.title).contains(q_lower)
                | func.lower(Deal.company).contains(q_lower)
            ),
        )
        .limit(limit)
    )
    deals = deal_result.scalars().all()

    task_result = await db.execute(
        select(Task)
        .where(
            Task.workspace_id == workspace_id,
            func.lower(Task.title).contains(q_lower),
        )
        .limit(limit)
    )
    tasks = task_result.scalars().all()

    return {
        "contacts": [
            {
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "company": c.company,
                "role": c.role,
                "status": c.status,
            }
            for c in contacts
        ],
        "deals": [
            {
                "id": str(d.id),
                "title": d.title,
                "company": d.company,
                "value": float(d.value or 0),
                "stage": d.stage,
            }
            for d in deals
        ],
        "tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "contact_id": str(t.contact_id) if t.contact_id else None,
            }
            for t in tasks
        ],
    }


@router.post("/workspaces/{workspace_id}/contacts/embed-all", status_code=202)
@limiter.limit("2/minute")
async def trigger_embed_all(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enqueue a Celery job to embed all contacts, returning the total count for progress tracking."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    count_result = await db.execute(
        text("SELECT COUNT(*) FROM contacts WHERE workspace_id = :wid"),
        {"wid": str(workspace_id)},
    )
    contacts_total: int = count_result.scalar() or 0

    from app.workers.embed_contacts import embed_workspace_contacts
    from app.routers.agents import _mark_job_dispatched

    task = embed_workspace_contacts.delay(str(workspace_id))
    _mark_job_dispatched(task.id, str(workspace_id))
    return {"job_id": task.id, "status": "queued", "contacts_total": contacts_total}
