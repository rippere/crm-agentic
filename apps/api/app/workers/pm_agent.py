"""
PM Agent — deployment health monitor.

Runs every 30 minutes. Catches silent failures:
  1. Agents stuck in 'processing' for >30 min → reset to idle, log error event
  2. Connectors with no sync in >48 hours → log warning event
  3. Logs a heartbeat so we know the worker is alive
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

STUCK_AGENT_THRESHOLD = timedelta(minutes=30)
STALE_CONNECTOR_THRESHOLD = timedelta(hours=48)


def _get_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    engine = create_async_engine(url, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_health_check() -> dict[str, Any]:
    from app.models.activity_event import ActivityEvent
    from app.models.agent import Agent
    from app.models.connector import Connector

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
                event = ActivityEvent(
                    workspace_id=agent.workspace_id,
                    type="pm_alert",
                    agent_name="PM Agent",
                    description=f"Agent '{agent.name}' was stuck in processing for >{STUCK_AGENT_THRESHOLD.seconds // 60}m — reset to error.",
                    severity="error",
                )
                db.add(event)
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
                event = ActivityEvent(
                    workspace_id=connector.workspace_id,
                    type="pm_alert",
                    agent_name="PM Agent",
                    description=f"{connector.service} connector hasn't synced in >{STALE_CONNECTOR_THRESHOLD.seconds // 3600}h. Last sync: {last.strftime('%Y-%m-%d %H:%M UTC')}",
                    severity="warning",
                )
                db.add(event)
                issues.append(f"stale_connector:{connector.service}:{connector.workspace_id}")
                logger.warning("pm_agent stale_connector service=%s workspace=%s", connector.service, connector.workspace_id)

        # 3. Heartbeat — one event per workspace that has agents
        result = await db.execute(select(Agent.workspace_id).distinct())
        workspace_ids = [row[0] for row in result.all()]
        for ws_id in workspace_ids:
            heartbeat = ActivityEvent(
                workspace_id=ws_id,
                type="pm_heartbeat",
                agent_name="PM Agent",
                description=f"Health check passed. Issues detected: {len(issues)}",
                severity="info" if not issues else "warning",
            )
            db.add(heartbeat)

        await db.commit()

    return {"issues": issues, "checked_agents": len(stuck_agents), "checked_connectors": len(connectors)}


@celery_app.task(name="app.workers.pm_agent.run_health_check", bind=True)
def run_health_check(self: Any) -> dict[str, Any]:
    """PM Agent: catch silent failures across agents and connectors."""
    return asyncio.get_event_loop().run_until_complete(_run_health_check())
