import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EscalationDecision(Base):
    """Append-only audit of every escalation-graph decision (Inc 2).

    Mirrors ``025_escalation_controls.sql`` verbatim and the append-only shape of
    ``engagement_events`` (``occurred_at`` + ``created_at``, NO ``updated_at``).
    One row is written per per-enrollment decision by the sequence tick (and by
    the human call-outcome path, ``decided_by='human'``). ``decided_by`` carries
    the future model-governed seam (``'model'``); today the tick writes
    ``'threshold'`` and the operator path writes ``'human'``.

    ``sentiment`` uses the R8 TEXT vocab
    (positive|neutral|negative|objection|booking|unsubscribe); ``proposed_action``
    is the pre-clamp intent and ``final_action`` the post-clamp outcome — an
    ``ask`` clamp turns a proposed ``send`` into a ``park``, ``off`` into ``hold``.
    """

    __tablename__ = "escalation_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sequence_enrollments.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_action: Mapped[str] = mapped_column(Text, nullable=False)
    final_action: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String, nullable=False, default="threshold")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
