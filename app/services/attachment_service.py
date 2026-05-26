"""Attachment service for file attachment operations."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment

logger = logging.getLogger(__name__)


class AttachmentService:
    """Service for creating and retrieving file attachments.

    Attachments are associated with entries and track file metadata
    including Telegram file IDs for deferred downloads.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_attachment(
        self,
        entry_id: int,
        file_type: str,
        telegram_file_id: str | None = None,
        file_name: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        metadata: dict | None = None,
    ) -> Attachment:
        """Create a new attachment associated with an entry.

        Args:
            entry_id: The parent entry's primary key.
            file_type: Type of file ('photo', 'document', 'voice', 'audio', 'video').
            telegram_file_id: Telegram file ID for later retrieval.
            file_name: Original file name.
            mime_type: MIME type of the file.
            file_size: File size in bytes.
            metadata: Additional JSONB metadata.

        Returns:
            The created Attachment.
        """
        attachment = Attachment(
            entry_id=entry_id,
            file_type=file_type,
            telegram_file_id=telegram_file_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            metadata_=metadata or {},
        )

        self.db.add(attachment)
        await self.db.flush()

        logger.info(
            "Created attachment id=%s for entry_id=%s type=%s name=%s",
            attachment.id,
            entry_id,
            file_type,
            file_name,
        )
        return attachment

    async def get_attachments(self, entry_id: int) -> list[Attachment]:
        """Get all attachments for a given entry.

        Args:
            entry_id: The parent entry's primary key.

        Returns:
            List of Attachment objects ordered by creation date.
        """
        stmt = (
            select(Attachment)
            .where(Attachment.entry_id == entry_id)
            .order_by(Attachment.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
