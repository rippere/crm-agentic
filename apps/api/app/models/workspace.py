import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="sales")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="workspace")  # noqa: F821
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="workspace")  # noqa: F821
    deals: Mapped[list["Deal"]] = relationship("Deal", back_populates="workspace")  # noqa: F821
    agents: Mapped[list["Agent"]] = relationship("Agent", back_populates="workspace")  # noqa: F821
    connectors: Mapped[list["Connector"]] = relationship("Connector", back_populates="workspace")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="workspace")  # noqa: F821
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="workspace")  # noqa: F821
