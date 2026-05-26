"""Search service for full-text search and tag-based queries."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entry import Entry
from app.models.tag import Tag, entry_tags

logger = logging.getLogger(__name__)


class SearchService:
    """Service for full-text search, tag-based search, and tag analytics.

    Uses PostgreSQL's built-in tsvector/tsquery for full-text search
    with ranking and headline generation.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def full_text_search(
        self,
        query: str,
        entry_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Perform full-text search across entries.

        Uses PostgreSQL websearch_to_tsquery for natural language query
        parsing, ts_rank for relevance ordering, and ts_headline for
        generating content snippets with highlighted matches.

        Args:
            query: Search query string (supports natural language syntax).
            entry_type: Optional filter by entry type.
            tags: Optional filter by tag names (entries must have ALL tags).
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            Tuple of (list of result dicts, total count).
            Each dict has keys: 'entry', 'rank', 'headline'.
        """
        if not query or not query.strip():
            return [], 0

        ts_query = func.websearch_to_tsquery("english", query)
        ts_rank = func.ts_rank(Entry.search_vector, ts_query)
        ts_headline = func.ts_headline(
            "english",
            Entry.content,
            ts_query,
            "StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=20",
        )

        # Base filter: search vector matches query and not archived
        base_filter = Entry.search_vector.op("@@")(ts_query)
        conditions = [base_filter, Entry.is_archived == False]  # noqa: E712

        if entry_type is not None:
            conditions.append(Entry.entry_type == entry_type)

        # Tag filtering: entry must be associated with all specified tags
        if tags:
            for tag_name in tags:
                tag_subq = (
                    select(entry_tags.c.entry_id)
                    .join(Tag, Tag.id == entry_tags.c.tag_id)
                    .where(Tag.name == tag_name.lower().strip())
                )
                conditions.append(Entry.id.in_(tag_subq))

        # Count query
        count_stmt = (
            select(func.count())
            .select_from(Entry)
            .where(*conditions)
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        if total == 0:
            return [], 0

        # Main search query
        stmt = (
            select(Entry, ts_rank.label("rank"), ts_headline.label("headline"))
            .where(*conditions)
            .options(selectinload(Entry.tags))
            .order_by(ts_rank.desc(), Entry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        results = [
            {
                "entry": row.Entry,
                "rank": float(row.rank),
                "headline": row.headline,
            }
            for row in rows
        ]

        logger.info("Full-text search query=%r found %d results (total=%d)", query, len(results), total)
        return results, total

    async def search_by_tag(self, tag_name: str, limit: int = 20) -> list[Entry]:
        """Search entries by a specific tag name.

        Args:
            tag_name: The tag name to search for (case-insensitive).
            limit: Maximum number of results.

        Returns:
            List of entries that have the specified tag.
        """
        normalized = tag_name.lower().strip()

        stmt = (
            select(Entry)
            .join(entry_tags, Entry.id == entry_tags.c.entry_id)
            .join(Tag, Tag.id == entry_tags.c.tag_id)
            .where(Tag.name == normalized)
            .where(Entry.is_archived == False)  # noqa: E712
            .options(selectinload(Entry.tags))
            .order_by(Entry.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_tags_with_counts(self) -> list[dict]:
        """Get all tags with their entry counts.

        Returns:
            List of dicts with 'tag' and 'count' keys, ordered by
            count descending.
        """
        stmt = (
            select(Tag, func.count(entry_tags.c.entry_id).label("entry_count"))
            .outerjoin(entry_tags, Tag.id == entry_tags.c.tag_id)
            .group_by(Tag.id)
            .order_by(func.count(entry_tags.c.entry_id).desc(), Tag.name)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            {
                "tag": row.Tag,
                "count": row.entry_count,
            }
            for row in rows
        ]
