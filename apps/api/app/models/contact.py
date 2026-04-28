import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, DateTime, ForeignKey, Numeric, Integer, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="lead")
    ml_score: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"value": 50, "label": "warm", "trend": "stable", "signals": []})
    semantic_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_activity: Mapped[str] = mapped_column(String, nullable=False, default="Never")
    revenue: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    deal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="contacts")  # noqa: F821
    deals: Mapped[list["Deal"]] = relationship("Deal", back_populates="contact")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="contact")  # noqa: F821
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="contact")  # noqa: F821
