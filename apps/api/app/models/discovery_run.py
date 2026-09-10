import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DiscoveryRun(Base):
    """Run bookkeeping for a long-running market-discovery job (Autonomous Lead
    Engine, Increment 1). Mirrors ``024_lead_engine_discovery.sql`` verbatim —
    column names, types and nullability match the migration exactly.

    A row is created ``status='queued'`` by ``services.discovery.dispatch_discovery_run``
    (committed before the Celery task is dispatched, so a fast worker finds it),
    then driven through ``running`` → ``succeeded``/``partial``/``failed`` by
    ``workers.discovery.run_market_discovery``. Discovered venues become rows in
    the existing ``leads`` table (``source='discovery'``); this table only tracks
    the run itself.
    """

    __tablename__ = "discovery_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    locality: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rubric: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
