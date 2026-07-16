import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    """A single email (or Slack message) belonging to a workspace.

    Two naming traps in the header columns added by migration 022:

    * ``rfc_message_id`` is the RFC 5322 ``Message-ID`` *header* — a string like
      ``<CAF=abc@mail.example.com>``. It is not a foreign key and not this row's
      ``id``. Everywhere else in this codebase ``message_id`` means an FK to
      ``messages.id`` (Task, ClarityScore), hence the ``rfc_`` prefix.
    * ``received_at`` is the message's own timestamp in BOTH directions — when it
      arrived (inbound) or when it was sent (outbound). Read it alongside
      ``direction`` rather than expecting a separate ``sent_at``.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    connector_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("connectors.id", ondelete="SET NULL"), nullable=True)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body_plain: Mapped[str] = mapped_column(String, nullable=False)
    sender_email: Mapped[str | None] = mapped_column(String, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Header capture (migration 022) — the graph and reply detection read these.
    to_emails: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cc_emails: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    rfc_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    in_reply_to: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[str | None] = mapped_column(String, nullable=True)

    # TRUE = metadata-only row: headers kept for the relationship graph, body
    # never stored, hidden from every message-facing read path. Distinct from
    # `relevant`, which stays the LLM's judgment and keeps its existing meaning.
    graph_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="messages")  # noqa: F821
    connector: Mapped["Connector"] = relationship("Connector", back_populates="messages")  # noqa: F821
    contact: Mapped["Contact"] = relationship("Contact", back_populates="messages")  # noqa: F821
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="message")  # noqa: F821
    clarity_score: Mapped["ClarityScore"] = relationship("ClarityScore", back_populates="message", uselist=False)  # noqa: F821
