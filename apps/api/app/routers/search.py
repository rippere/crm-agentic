"""
Semantic search endpoints.

GET  /workspaces/{id}/contacts/search?q=<text>&limit=<n>
  — Returns contacts ranked by cosine similarity to query embedding.
  — Falls back to ILIKE name/company search if no embeddings exist yet.

POST /workspaces/{id}/contacts/embed
  — Enqueues a Celery task to embed all workspace contacts.
"""
from __future__ import annotations

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.contact import Contact
from app.models.user import User

router = APIRouter()


@router.get("/workspaces/{workspace_id}/contacts/search")
async def semantic_search(
    workspace_id: uuid_mod.UUID,
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
        like = f"%{q}%"
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
    workspace_id: uuid_mod.UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enqueue a Celery job to embed all contacts in this workspace."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.workers.embed_contacts import embed_workspace_contacts

    task = embed_workspace_contacts.delay(str(workspace_id))
    return {"job_id": task.id, "status": "queued"}
