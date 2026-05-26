"""Core Entry model — the unified entity for all knowledge items."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class EntryType(str, enum.Enum):
    """Discriminator for the type of knowledge entry."""

    NOTE = "note"
    TASK = "task"
    BOOKMARK = "bookmark"
    CODE = "code"
    VOICE = "voice"
    IDEA = "idea"
    LEARNING = "learning"
    DECISION = "decision"
    MEMORY = "memory"
    DOCUMENT = "document"


class TaskStatus(str, enum.Enum):
    """Status for task-type entries."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Entry(TimestampMixin, Base):
    """The core model — every piece of knowledge is an Entry.

    Notes, tasks, bookmarks, code snippets, voice memos, ideas, learnings,
    decisions, memories, and documents are all stored in this single table
    with an entry_type discriminator.
    """

    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="telegram")
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    task_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    task_due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_: Mapped[dict] = Column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    search_vector = Column(TSVECTOR)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Relationships
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        secondary="entry_tags",
        back_populates="entries",
        lazy="selectin",
    )
    attachments: Mapped[list[Attachment]] = relationship(
        "Attachment",
        back_populates="entry",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_entries_search_vector", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Entry(id={self.id}, type={self.entry_type}, title={self.title!r})>"


# Resolve forward references after all models are imported
from app.models.attachment import Attachment  # noqa: E402
from app.models.tag import Tag  # noqa: E402
