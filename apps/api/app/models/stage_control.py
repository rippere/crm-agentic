import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StageControl(Base):
    """Per-workspace × per-stage autonomy cap (Autonomous Lead Engine, Inc 2).

    Mirrors ``025_escalation_controls.sql`` verbatim. This is the ONE table the
    shared authority resolver (``app.services.authority.resolve_authority``) reads
    to clamp every outward send — both the sequence tick and the chatbot action
    bus resolve against it (R11). ``mode`` defaults to ``'ask'`` (R12 fail-closed);
    a workspace with no row for a stage falls back to
    ``escalation.DEFAULT_STAGE_MODE[stage]`` (also ``'ask'``).
    """

    __tablename__ = "stage_controls"
    __table_args__ = (UniqueConstraint("workspace_id", "stage", name="stage_controls_workspace_id_stage_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="ask")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
