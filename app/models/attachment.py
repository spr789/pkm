"""Attachment model for files associated with entries."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Attachment(TimestampMixin, Base):
    """A file attachment linked to an Entry.

    Supports images, audio, documents, and video files.
    Telegram file IDs are stored for efficient re-download.
    """

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict] = Column("metadata", JSONB, nullable=False, default=dict, server_default="{}")

    # Relationships
    entry: Mapped[Entry] = relationship("Entry", back_populates="attachments")

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id}, type={self.file_type}, name={self.file_name!r})>"


# Resolve forward reference
from app.models.entry import Entry  # noqa: E402
