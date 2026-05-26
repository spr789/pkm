"""Entry service for CRUD operations on entries."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entry import Entry, EntryType, TaskStatus
from app.models.tag import Tag

logger = logging.getLogger(__name__)


class EntryService:
    """Service for creating, reading, updating, and managing entries.

    All methods operate within the provided async session. The caller
    is responsible for committing/rolling back the session when used
    outside of a context manager.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_entry(
        self,
        entry_type: str | EntryType,
        content: str,
        title: str | None = None,
        url: str | None = None,
        language: str | None = None,
        task_status: str | TaskStatus | None = None,
        source: str = "telegram",
        source_message_id: int | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Entry:
        """Create a new entry with optional tags.

        Args:
            entry_type: Type of entry (note, task, bookmark, etc.).
            content: Main content of the entry.
            title: Optional title; auto-generated from content if None.
            url: URL for bookmark entries.
            language: Programming language for code entries.
            task_status: Status for task entries; defaults to TODO.
            source: Where the entry came from (default: telegram).
            source_message_id: Telegram message ID for reference.
            tags: List of tag names to associate.
            metadata: Additional JSONB metadata.

        Returns:
            The created Entry with tags and attachments loaded.
        """
        # Normalize entry_type to enum value string
        if isinstance(entry_type, EntryType):
            entry_type_value = entry_type.value
        else:
            entry_type_value = entry_type

        # Auto-generate title from content if not provided
        if title is None and content:
            title = content[:100].split("\n")[0].strip()
            if len(title) < len(content):
                title = title[:97] + "..."

        # Default task status for task entries
        if entry_type_value == EntryType.TASK.value and task_status is None:
            task_status = TaskStatus.TODO

        # Normalize task_status
        if isinstance(task_status, TaskStatus):
            task_status_value = task_status.value
        elif task_status is not None:
            task_status_value = task_status
        else:
            task_status_value = None

        entry = Entry(
            entry_type=entry_type_value,
            content=content,
            title=title,
            url=url,
            language=language,
            task_status=task_status_value,
            source=source,
            source_message_id=source_message_id,
            metadata_=metadata or {},
        )

        # Handle tags
        if tags:
            tag_objects = await self._get_or_create_tags(tags)
            entry.tags = tag_objects

        self.db.add(entry)
        await self.db.flush()

        # Reload with relationships
        await self.db.refresh(entry, attribute_names=["tags", "attachments"])
        logger.info(
            "Created entry id=%s type=%s title=%s",
            entry.id,
            entry.entry_type,
            entry.title,
        )
        return entry

    async def get_entry(self, entry_id: int) -> Entry | None:
        """Get an entry by ID with tags and attachments loaded.

        Args:
            entry_id: The entry's primary key.

        Returns:
            The Entry or None if not found.
        """
        stmt = (
            select(Entry)
            .where(Entry.id == entry_id)
            .options(selectinload(Entry.tags), selectinload(Entry.attachments))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        entry_type: str | None = None,
        is_archived: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Entry], int]:
        """List entries with optional type filter and pagination.

        Args:
            entry_type: Filter by entry type (e.g., 'note', 'task').
            is_archived: Whether to include archived entries.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            Tuple of (list of entries, total count).
        """
        base = select(Entry).where(Entry.is_archived == is_archived)
        if entry_type is not None:
            base = base.where(Entry.entry_type == entry_type)

        # Total count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Fetch entries
        stmt = (
            base.options(selectinload(Entry.tags), selectinload(Entry.attachments))
            .order_by(Entry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        entries = list(result.scalars().all())

        return entries, total

    async def update_entry(self, entry_id: int, **kwargs) -> Entry | None:
        """Partially update an entry.

        Args:
            entry_id: The entry's primary key.
            **kwargs: Fields to update (e.g., title='New Title', content='...').

        Returns:
            The updated Entry or None if not found.
        """
        entry = await self.get_entry(entry_id)
        if entry is None:
            return None

        # Handle tags separately
        tag_names = kwargs.pop("tags", None)
        if tag_names is not None:
            tag_objects = await self._get_or_create_tags(tag_names)
            entry.tags = tag_objects

        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)

        entry.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(entry, attribute_names=["tags", "attachments"])

        logger.info("Updated entry id=%s fields=%s", entry_id, list(kwargs.keys()))
        return entry

    async def archive_entry(self, entry_id: int) -> bool:
        """Archive an entry by setting is_archived=True.

        Args:
            entry_id: The entry's primary key.

        Returns:
            True if the entry was found and archived, False otherwise.
        """
        entry = await self.get_entry(entry_id)
        if entry is None:
            return False

        entry.is_archived = True
        entry.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info("Archived entry id=%s", entry_id)
        return True

    async def pin_entry(self, entry_id: int) -> bool:
        """Toggle the pinned state of an entry.

        Args:
            entry_id: The entry's primary key.

        Returns:
            True if the entry was found and toggled, False otherwise.
        """
        entry = await self.get_entry(entry_id)
        if entry is None:
            return False

        entry.is_pinned = not entry.is_pinned
        entry.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info("Toggled pin for entry id=%s, is_pinned=%s", entry_id, entry.is_pinned)
        return True

    async def get_recent(self, limit: int = 10) -> list[Entry]:
        """Get the most recent non-archived entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of entries ordered by creation date descending.
        """
        stmt = (
            select(Entry)
            .where(Entry.is_archived == False)  # noqa: E712
            .options(selectinload(Entry.tags))
            .order_by(Entry.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_tasks(self, status: str | None = None) -> list[Entry]:
        """Get all task entries, optionally filtered by status.

        Args:
            status: Filter by task status ('todo', 'in_progress', 'done').

        Returns:
            List of task entries ordered by creation date descending.
        """
        stmt = (
            select(Entry)
            .where(Entry.entry_type == EntryType.TASK.value)
            .where(Entry.is_archived == False)  # noqa: E712
            .options(selectinload(Entry.tags))
        )

        if status is not None:
            stmt = stmt.where(Entry.task_status == status)

        stmt = stmt.order_by(Entry.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def complete_task(self, entry_id: int) -> Entry | None:
        """Mark a task entry as done.

        Args:
            entry_id: The entry's primary key.

        Returns:
            The updated Entry or None if not found or not a task.
        """
        entry = await self.get_entry(entry_id)
        if entry is None:
            return None

        if entry.entry_type != EntryType.TASK.value:
            logger.warning("Entry id=%s is not a task (type=%s)", entry_id, entry.entry_type)
            return None

        entry.task_status = TaskStatus.DONE.value
        entry.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(entry, attribute_names=["tags", "attachments"])

        logger.info("Completed task id=%s", entry_id)
        return entry

    async def update_ai_metadata(
        self,
        entry_id: int,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> Entry | None:
        """Update an entry with AI-generated summary and/or tags.

        Called by the AI processing pipeline after background analysis.

        Args:
            entry_id: The entry's primary key.
            summary: AI-generated summary text.
            tags: List of AI-suggested tag names.

        Returns:
            The updated Entry or None if not found.
        """
        entry = await self.get_entry(entry_id)
        if entry is None:
            return None

        if summary is not None:
            entry.summary = summary

        if tags is not None:
            # Merge AI tags with existing tags
            existing_tag_names = {tag.name for tag in entry.tags}
            new_tag_names = [t for t in tags if t.lower().strip() not in existing_tag_names]
            if new_tag_names:
                new_tag_objects = await self._get_or_create_tags(new_tag_names)
                entry.tags = list(entry.tags) + new_tag_objects

        entry.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(entry, attribute_names=["tags", "attachments"])

        logger.info("Updated AI metadata for entry id=%s", entry_id)
        return entry

    async def _get_or_create_tags(self, tag_names: list[str]) -> list[Tag]:
        """Get existing tags or create new ones.

        Args:
            tag_names: List of tag name strings.

        Returns:
            List of Tag objects.
        """
        tags: list[Tag] = []
        for name in tag_names:
            normalized = name.lower().strip()
            if not normalized:
                continue

            stmt = select(Tag).where(Tag.name == normalized)
            result = await self.db.execute(stmt)
            tag = result.scalar_one_or_none()

            if tag is None:
                tag = Tag(name=normalized)
                self.db.add(tag)
                await self.db.flush()

            tags.append(tag)

        return tags
