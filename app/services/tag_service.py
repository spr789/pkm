"""Tag service for tag management operations."""

from __future__ import annotations

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, entry_tags

logger = logging.getLogger(__name__)


class TagService:
    """Service for creating, listing, and managing tags.

    Handles tag normalization (lowercase, stripped), deduplication,
    and tag merging operations.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_tag(
        self,
        name: str,
        category: str | None = None,
    ) -> Tag:
        """Get an existing tag by name or create a new one.

        Tag names are normalized to lowercase with whitespace stripped.

        Args:
            name: The tag name.
            category: Optional category for the tag.

        Returns:
            The existing or newly created Tag.
        """
        normalized = name.lower().strip()
        if not normalized:
            raise ValueError("Tag name cannot be empty")

        stmt = select(Tag).where(Tag.name == normalized)
        result = await self.db.execute(stmt)
        tag = result.scalar_one_or_none()

        if tag is not None:
            # Update category if provided and not already set
            if category is not None and tag.category is None:
                tag.category = category
                await self.db.flush()
            return tag

        tag = Tag(name=normalized, category=category)
        self.db.add(tag)
        await self.db.flush()

        logger.info("Created new tag name=%r category=%r", normalized, category)
        return tag

    async def get_or_create_tags(self, names: list[str]) -> list[Tag]:
        """Batch get-or-create for multiple tag names.

        Args:
            names: List of tag name strings.

        Returns:
            List of Tag objects (existing or newly created).
        """
        tags: list[Tag] = []
        for name in names:
            normalized = name.lower().strip()
            if not normalized:
                continue
            tag = await self.get_or_create_tag(normalized)
            tags.append(tag)
        return tags

    async def list_tags(self) -> list[Tag]:
        """List all tags ordered alphabetically by name.

        Returns:
            List of all Tag objects.
        """
        stmt = select(Tag).order_by(Tag.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def merge_tags(self, source_name: str, target_name: str) -> bool:
        """Merge one tag into another.

        All entries associated with the source tag are re-associated
        with the target tag. The source tag is then deleted. If an entry
        already has the target tag, the duplicate association is skipped.

        Args:
            source_name: Name of the tag to merge from (will be deleted).
            target_name: Name of the tag to merge into (will be kept).

        Returns:
            True if the merge was successful, False if either tag
            was not found.
        """
        source_normalized = source_name.lower().strip()
        target_normalized = target_name.lower().strip()

        if source_normalized == target_normalized:
            logger.warning("Cannot merge tag into itself: %r", source_normalized)
            return False

        # Find both tags
        source_stmt = select(Tag).where(Tag.name == source_normalized)
        source_result = await self.db.execute(source_stmt)
        source_tag = source_result.scalar_one_or_none()

        if source_tag is None:
            logger.warning("Source tag not found: %r", source_normalized)
            return False

        target_tag = await self.get_or_create_tag(target_normalized)

        # Get entry IDs associated with source tag
        source_entries_stmt = select(entry_tags.c.entry_id).where(
            entry_tags.c.tag_id == source_tag.id
        )
        source_entry_ids_result = await self.db.execute(source_entries_stmt)
        source_entry_ids = {row[0] for row in source_entry_ids_result.all()}

        # Get entry IDs already associated with target tag
        target_entries_stmt = select(entry_tags.c.entry_id).where(
            entry_tags.c.tag_id == target_tag.id
        )
        target_entry_ids_result = await self.db.execute(target_entries_stmt)
        target_entry_ids = {row[0] for row in target_entry_ids_result.all()}

        # Move entries from source to target (skip those already on target)
        entries_to_move = source_entry_ids - target_entry_ids
        if entries_to_move:
            await self.db.execute(
                update(entry_tags)
                .where(entry_tags.c.tag_id == source_tag.id)
                .where(entry_tags.c.entry_id.in_(entries_to_move))
                .values(tag_id=target_tag.id)
            )

        # Delete remaining source associations (duplicates)
        await self.db.execute(
            delete(entry_tags).where(entry_tags.c.tag_id == source_tag.id)
        )

        # Delete the source tag
        await self.db.delete(source_tag)
        await self.db.flush()

        logger.info(
            "Merged tag %r into %r, moved %d entries",
            source_normalized,
            target_normalized,
            len(entries_to_move),
        )
        return True
