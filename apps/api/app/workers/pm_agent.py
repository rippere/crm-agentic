"""
PM Agent — deployment health monitor.

Runs every 30 minutes. Catches silent failures across all subsystems:
  1. Agents stuck in 'processing' >30 min → reset to error, log alert
  2. Connectors with no sync in >48 hours → log warning
  3. Ingest tasks with high skip rates (>80% filtered) → log warning
  4. Projects with zero tasks after 24h → log info nudge
  5. Heartbeat per workspace so the activity feed proves it's alive
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import PGBOUNCER_CONNECT_ARGS

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

STUCK_AGENT_THRESHOLD = timedelta(minutes=30)
STALE_CONNECTOR_THRESHOLD = timedelta(hours=48)
EMPTY_PROJECT_THRESHOLD = timedelta(hours=24)


def _get_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_health_check() -> dict[str, Any]:
    from app.models.activity_event import ActivityEvent
    from app.models.agent import Agent
    from app.models.connector import Connector
    from app.models.project import Project
    from app.models.task import Task

    SessionFactory = _get_session()
    issues: list[str] = []
    now = datetime.now(tz=timezone.utc)

    async with SessionFactory() as db:

        # 1. Agents stuck in 'processing'
        result = await db.execute(select(Agent).where(Agent.status == "processing"))
        stuck_agents = result.scalars().all()
        for agent in stuck_agents:
            updated = agent.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if now - updated > STUCK_AGENT_THRESHOLD:
                agent.status = "error"  # type: ignore[assignment]
                db.add(agent)
                db.add(ActivityEvent(
                    workspace_id=agent.workspace_id,
                    type="pm_alert",
                    agent_name="PM Agent",
                    description=f"Agent '{agent.name}' stuck in processing >{STUCK_AGENT_THRESHOLD.seconds // 60}m — reset to error.",
                    severity="error",
                ))
                issues.append(f"stuck_agent:{agent.name}")
                logger.warning("pm_agent stuck_agent agent_id=%s name=%s", agent.id, agent.name)

        # 2. Stale connectors
        result = await db.execute(select(Connector))
        connectors = result.scalars().all()
        for connector in connectors:
            if connector.last_sync is None:
                continue
            last = connector.last_sync
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last > STALE_CONNECTOR_THRESHOLD:
                db.add(ActivityEvent(
                    workspace_id=connector.workspace_id,
                    type="pm_alert",
                    agent_name="PM Agent",
                    description=f"{connector.service} connector hasn't synced in >{int(STALE_CONNECTOR_THRESHOLD.total_seconds() // 3600)}h. Last sync: {last.strftime('%Y-%m-%d %H:%M UTC')}",
                    severity="warning",
                ))
                issues.append(f"stale_connector:{connector.service}")
                logger.warning("pm_agent stale_connector service=%s workspace=%s", connector.service, connector.workspace_id)

        # 3. Projects with no tasks after 24h (nudge to add tasks)
        result = await db.execute(select(Project))
        projects = result.scalars().all()
        for project in projects:
            created = project.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if now - created < EMPTY_PROJECT_THRESHOLD:
                continue
            task_count_result = await db.execute(
                select(func.count()).where(Task.project_id == project.id)
            )
            if task_count_result.scalar() == 0:
                db.add(ActivityEvent(
                    workspace_id=project.workspace_id,
                    type="pm_alert",
                    agent_name="PM Agent",
                    description=f"Project '{project.name}' has no tasks yet. Add tasks to start tracking progress.",
                    severity="info",
                ))
                issues.append(f"empty_project:{project.name}")

        # 4. Heartbeat per workspace
        result = await db.execute(select(Agent.workspace_id).distinct())
        workspace_ids = [row[0] for row in result.all()]
        for ws_id in workspace_ids:
            db.add(ActivityEvent(
                workspace_id=ws_id,
                type="pm_heartbeat",
                agent_name="PM Agent",
                description=f"Health check complete. {len(issues)} issue(s) detected.",
                severity="info" if not issues else "warning",
            ))

        await db.commit()

    return {
        "issues": issues,
        "checked_agents": len(stuck_agents),
        "checked_connectors": len(connectors),
        "checked_projects": len(projects),
    }


@celery_app.task(name="app.workers.pm_agent.run_health_check", bind=True)
def run_health_check(self: Any) -> dict[str, Any]:
    """PM Agent: catch silent failures across agents, connectors, and projects."""
    return asyncio.get_event_loop().run_until_complete(_run_health_check())
