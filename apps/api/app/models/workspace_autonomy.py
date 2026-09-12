import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WorkspaceAutonomy(Base):
    """Workspace-level autonomy master switch (Autonomous Lead Engine, Inc 2, R12).

    Mirrors ``025_escalation_controls.sql`` verbatim. ``autonomy_enabled`` defaults
    ``FALSE`` — until an operator flips it on, the authority resolver forces every
    actuating proposal to ``ask``/``off`` regardless of any per-stage ``auto`` in
    ``stage_controls`` (fail-closed, R11/R12). One row per workspace
    (``workspace_id`` UNIQUE).
    """

    __tablename__ = "workspace_autonomy"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    autonomy_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
