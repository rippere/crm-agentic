"""
NovaCRM native MCP server — streamable HTTP transport (MCP spec 2024-11-05).

Endpoint: POST /mcp
Auth:      Bearer token (same JWT used by the rest of the API)

Supported tools:
  - list_contacts     : search / list contacts in a workspace
  - list_deals        : filter deals by stage or health
  - stale_deals       : return deals with health_score <= threshold
  - pipeline_summary  : aggregate pipeline statistics
  - ask_crm           : free-text AI query over CRM data
  - list_tasks        : list the task work-queue (filter by status / project)
  - upsert_task       : idempotent create-or-update a task by external_id
  - update_task_status: status-only transition of a task by external_id

The task tools return compact JSON (not prose) because they are consumed by
automation — the auto-dev / fleet-dispatch agents — rather than read by a human.
"""

import uuid
from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User

router = APIRouter()

# ──────────────────────────────────────────────────────────────
# Tool registry
# ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_contacts",
        "description": "Search or list contacts in the CRM workspace. Returns name, email, company, role, status, and ML lead score.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional name/email/company filter"},
                "status": {"type": "string", "description": "Filter by status: lead, prospect, customer, churned"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    {
        "name": "list_deals",
        "description": "List active deals in the CRM, optionally filtered by stage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "description": "Filter by deal stage: discovery, qualified, proposal, negotiation, closed_won, closed_lost"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    {
        "name": "stale_deals",
        "description": "Return deals with a health score at or below a threshold (default 40). Useful for finding at-risk deals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "integer", "description": "Health score threshold (default 40)"},
            },
            "required": [],
        },
    },
    {
        "name": "pipeline_summary",
        "description": "Aggregate pipeline statistics: total value, win rate, deals by stage.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ask_crm",
        "description": "Ask a free-text question answered by Nova (Claude) over the live CRM workspace — pipeline, deals, contacts, tasks, recent activity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The natural-language question to answer over CRM data"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List tasks in the CRM work-queue, optionally filtered by status or project. Returns compact JSON (external_id, title, status, project_id, description, due_date) for automation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: open, in_progress, done, cancelled"},
                "project_id": {"type": "string", "description": "Filter by project UUID"},
                "limit": {"type": "integer", "description": "Max results (default 100)"},
            },
            "required": [],
        },
    },
    {
        "name": "upsert_task",
        "description": "Idempotent create-or-update of a task keyed on external_id. Re-calling with the same external_id updates the existing task instead of duplicating. Returns compact JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_id": {"type": "string", "description": "Stable idempotency key (e.g. cc:..., sync-..., auto-...)"},
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task body (default empty)"},
                "status": {"type": "string", "description": "open, in_progress, done, cancelled (default open)"},
                "project_id": {"type": "string", "description": "Optional project UUID to link the task to"},
            },
            "required": ["external_id", "title"],
        },
    },
    {
        "name": "update_task_status",
        "description": "Status-only transition of an existing task identified by external_id (e.g. claim open->in_progress, complete ->done). Leaves all other fields untouched. Returns compact JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_id": {"type": "string", "description": "The task's stable external_id"},
                "status": {"type": "string", "description": "New status: open, in_progress, done, cancelled"},
            },
            "required": ["external_id", "status"],
        },
    },
]


# ──────────────────────────────────────────────────────────────
# Tool handlers
# ──────────────────────────────────────────────────────────────

async def _list_contacts(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    from app.models.contact import Contact

    query = args.get("query", "").lower()
    status_filter = args.get("status")
    limit = int(args.get("limit", 20))

    stmt = select(Contact).where(Contact.workspace_id == workspace_id)
    if status_filter:
        stmt = stmt.where(Contact.status == status_filter)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    contacts = result.scalars().all()

    if query:
        contacts = [
            c for c in contacts
            if query in (c.name or "").lower()
            or query in (c.email or "").lower()
            or query in (c.company or "").lower()
        ]

    lines = [f"Found {len(contacts)} contact(s):\n"]
    for c in contacts:
        score = (c.ml_score or {}).get("value", "?") if isinstance(c.ml_score, dict) else "?"
        lines.append(f"- {c.name} ({c.email}) | {c.company} | {c.role} | Status: {c.status} | ML score: {score}")
    return "\n".join(lines)


async def _list_deals(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    from app.models.deal import Deal

    stage = args.get("stage")
    limit = int(args.get("limit", 20))

    stmt = select(Deal).where(Deal.workspace_id == workspace_id)
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    deals = result.scalars().all()

    lines = [f"Found {len(deals)} deal(s):\n"]
    for d in deals:
        lines.append(
            f"- {d.title or 'Untitled'} | {d.company} | Stage: {d.stage} | "
            f"Value: ${d.value:,.0f} | Win prob: {d.ml_win_probability}% | Health: {d.health_score}"
        )
    return "\n".join(lines)


async def _stale_deals(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    from app.models.deal import Deal
    from sqlalchemy import asc

    threshold = int(args.get("threshold", 40))

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.health_score <= threshold,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        ).order_by(asc(Deal.health_score)).limit(10)
    )
    deals = result.scalars().all()

    if not deals:
        return f"No deals with health score ≤ {threshold}. Pipeline looks healthy."

    lines = [f"Deals with health score ≤ {threshold}:\n"]
    for d in deals:
        lines.append(
            f"- {d.title or 'Untitled'} at {d.company} | Stage: {d.stage} | "
            f"Health: {d.health_score} | Value: ${d.value:,.0f}"
        )
    return "\n".join(lines)


async def _pipeline_summary(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    from app.models.deal import Deal

    result = await db.execute(select(Deal).where(Deal.workspace_id == workspace_id))
    deals = result.scalars().all()

    won = [d for d in deals if d.stage == "closed_won"]
    lost = [d for d in deals if d.stage == "closed_lost"]
    active = [d for d in deals if d.stage not in ("closed_won", "closed_lost")]
    closed = len(won) + len(lost)
    win_rate = round((len(won) / closed) * 100) if closed else 0
    pipeline_value = sum(d.value for d in active)
    won_value = sum(d.value for d in won)

    by_stage: dict[str, int] = {}
    for d in active:
        by_stage[d.stage] = by_stage.get(d.stage, 0) + 1

    stage_summary = ", ".join(f"{s}: {n}" for s, n in sorted(by_stage.items()))
    return (
        f"Pipeline Summary:\n"
        f"- Total deals: {len(deals)}\n"
        f"- Active: {len(active)} (${pipeline_value:,.0f} in pipeline)\n"
        f"- Closed Won: {len(won)} (${won_value:,.0f})\n"
        f"- Closed Lost: {len(lost)}\n"
        f"- Win rate: {win_rate}%\n"
        f"- Active by stage: {stage_summary or 'none'}"
    )


async def _ask_crm(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    from app.routers.ai import answer_crm_query

    query = (args.get("query") or "").strip()
    if not query:
        return "Provide a 'query' to ask the CRM."
    return await answer_crm_query(query, workspace_id, db)


_VALID_TASK_STATUS = {"open", "in_progress", "done", "cancelled"}


async def _list_tasks(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    import json
    from app.models.task import Task

    status_filter = args.get("status")
    project_id = args.get("project_id")
    limit = int(args.get("limit", 100))

    stmt = select(Task).where(Task.workspace_id == workspace_id)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    if project_id:
        stmt = stmt.where(Task.project_id == UUID(str(project_id)))
    stmt = stmt.order_by(Task.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    tasks = result.scalars().all()
    payload = [
        {
            "external_id": t.external_id,
            "title": t.title,
            "status": t.status,
            "project_id": str(t.project_id) if t.project_id else None,
            "description": t.description,
            "due_date": t.due_date.isoformat() if t.due_date else None,
        }
        for t in tasks
    ]
    return json.dumps(payload)


async def _upsert_task(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    import json
    from app.routers.tasks import upsert_task_record

    external_id = (args.get("external_id") or "").strip()
    title = (args.get("title") or "").strip()
    if not external_id or not title:
        return json.dumps({"error": "Both 'external_id' and 'title' are required."})

    new_status = args.get("status", "open")
    if new_status not in _VALID_TASK_STATUS:
        return json.dumps({"error": f"status must be one of {sorted(_VALID_TASK_STATUS)}"})

    project_id = args.get("project_id")
    task = await upsert_task_record(
        db,
        workspace_id,
        external_id,
        title=title,
        description=args.get("description", ""),
        status=new_status,
        project_id=UUID(str(project_id)) if project_id else None,
    )
    return json.dumps({
        "id": str(task.id),
        "external_id": task.external_id,
        "title": task.title,
        "status": task.status,
    })


async def _update_task_status(args: dict, workspace_id: UUID, db: AsyncSession) -> str:
    import json
    from app.models.task import Task

    external_id = (args.get("external_id") or "").strip()
    new_status = (args.get("status") or "").strip()
    if not external_id or new_status not in _VALID_TASK_STATUS:
        return json.dumps({
            "error": f"'external_id' required and 'status' must be one of {sorted(_VALID_TASK_STATUS)}"
        })

    result = await db.execute(
        select(Task).where(Task.workspace_id == workspace_id, Task.external_id == external_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        return json.dumps({"error": f"No task found with external_id={external_id}"})

    task.status = new_status  # type: ignore[assignment]
    await db.commit()
    await db.refresh(task)
    return json.dumps({"external_id": task.external_id, "status": task.status})


TOOL_HANDLERS = {
    "list_contacts": _list_contacts,
    "list_deals": _list_deals,
    "stale_deals": _stale_deals,
    "pipeline_summary": _pipeline_summary,
    "ask_crm": _ask_crm,
    "list_tasks": _list_tasks,
    "upsert_task": _upsert_task,
    "update_task_status": _update_task_status,
}


# ──────────────────────────────────────────────────────────────
# JSON-RPC endpoint
# ──────────────────────────────────────────────────────────────

def _ok(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


@router.post("/mcp")
@limiter.limit("20/minute")
async def mcp_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    method = body.get("method", "")
    req_id = body.get("id")
    params = body.get("params", {})

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "NovaCRM", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        })

    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return _err(req_id, -32601, f"Unknown tool: {tool_name}")

        workspace_id = current_user.workspace_id
        if workspace_id is None:
            return _err(req_id, -32603, "User has no workspace")

        try:
            text = await handler(arguments, workspace_id, db)
        except Exception as exc:
            return _err(req_id, -32603, str(exc))

        return _ok(req_id, {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        })

    return _err(req_id, -32601, f"Method not found: {method}")
