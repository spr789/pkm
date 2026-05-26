"""Snapshot service for periodic knowledge summaries."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entry import Entry
from app.models.snapshot import Snapshot, SnapshotPeriod

logger = logging.getLogger(__name__)


class SnapshotService:
    """Service for generating and retrieving periodic knowledge snapshots.

    Snapshots aggregate entries over daily, weekly, or monthly periods
    with computed statistics and optional AI-generated summaries.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate_snapshot(
        self,
        period: str,
        ai_service=None,
    ) -> Snapshot:
        """Generate a snapshot for the given period.

        Computes period boundaries, queries entries in that range,
        calculates statistics, and optionally generates an AI summary.

        Args:
            period: Snapshot period ('daily', 'weekly', 'monthly').
            ai_service: Optional AIProcessor instance for AI summaries.

        Returns:
            The created and persisted Snapshot.
        """
        period_start, period_end = self._compute_period_bounds(period)

        # Query entries in the period range
        stmt = (
            select(Entry)
            .where(
                Entry.created_at >= period_start,
                Entry.created_at <= period_end,
                Entry.is_archived == False,  # noqa: E712
            )
            .options(selectinload(Entry.tags))
            .order_by(Entry.created_at.desc())
        )
        result = await self.db.execute(stmt)
        entries = list(result.scalars().all())

        # Compute stats
        stats = self._compute_stats(entries)

        # Compute highlights (pinned entries and most-tagged)
        highlights = self._compute_highlights(entries)

        # Generate AI summary if service provided
        summary: str | None = None
        if ai_service is not None and entries:
            try:
                entries_text = self._format_entries_for_ai(entries)
                summary = await ai_service.generate_snapshot_summary(entries_text, period)
            except Exception:
                logger.exception("Failed to generate AI summary for %s snapshot", period)
                summary = None

        snapshot = Snapshot(
            period=period,
            period_start=period_start,
            period_end=period_end,
            summary=summary,
            stats=stats,
            highlights=highlights,
        )

        self.db.add(snapshot)
        await self.db.flush()

        logger.info(
            "Generated %s snapshot id=%s with %d entries",
            period,
            snapshot.id,
            len(entries),
        )
        return snapshot

    async def get_snapshots(
        self,
        period: str | None = None,
        limit: int = 10,
    ) -> list[Snapshot]:
        """Get snapshots, optionally filtered by period type.

        Args:
            period: Optional period filter ('daily', 'weekly', 'monthly').
            limit: Maximum number of snapshots to return.

        Returns:
            List of Snapshot objects ordered by period_start descending.
        """
        stmt = select(Snapshot).order_by(Snapshot.period_start.desc()).limit(limit)

        if period is not None:
            stmt = stmt.where(Snapshot.period == period)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_snapshot(self, period: str) -> Snapshot | None:
        """Get the most recent snapshot for a given period type.

        Args:
            period: The period type ('daily', 'weekly', 'monthly').

        Returns:
            The latest Snapshot or None if no snapshots exist.
        """
        stmt = (
            select(Snapshot)
            .where(Snapshot.period == period)
            .order_by(Snapshot.period_start.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _compute_period_bounds(self, period: str) -> tuple[datetime, datetime]:
        """Calculate period start and end dates.

        Args:
            period: Period type ('daily', 'weekly', 'monthly').

        Returns:
            Tuple of (period_start, period_end) as timezone-aware datetimes.
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        if period == SnapshotPeriod.DAILY.value:
            start_date = today
            end_date = today
        elif period == SnapshotPeriod.WEEKLY.value:
            start_date = today - timedelta(days=6)
            end_date = today
        elif period == SnapshotPeriod.MONTHLY.value:
            start_date = today - timedelta(days=29)
            end_date = today
        else:
            # Default to daily
            logger.warning("Unknown period %r, defaulting to daily", period)
            start_date = today
            end_date = today

        period_start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        period_end = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

        return period_start, period_end

    def _compute_stats(self, entries: list[Entry]) -> dict:
        """Compute aggregate statistics from a list of entries.

        Args:
            entries: List of Entry objects with tags loaded.

        Returns:
            Dict with total_count, count_by_type, count_by_tag, and
            other aggregate metrics.
        """
        type_counter: Counter[str] = Counter()
        tag_counter: Counter[str] = Counter()

        for entry in entries:
            type_counter[entry.entry_type] += 1
            for tag in entry.tags:
                tag_counter[tag.name] += 1

        return {
            "total_count": len(entries),
            "count_by_type": dict(type_counter.most_common()),
            "count_by_tag": dict(tag_counter.most_common(20)),
            "pinned_count": sum(1 for e in entries if e.is_pinned),
            "tasks_completed": sum(
                1 for e in entries
                if e.entry_type == "task" and e.task_status == "done"
            ),
            "tasks_pending": sum(
                1 for e in entries
                if e.entry_type == "task" and e.task_status != "done"
            ),
        }

    def _compute_highlights(self, entries: list[Entry]) -> list[dict]:
        """Extract highlight entries (pinned or with summaries).

        Args:
            entries: List of Entry objects.

        Returns:
            List of dicts with 'id', 'title', 'type', and 'summary' keys.
        """
        highlights: list[dict] = []

        for entry in entries:
            if entry.is_pinned or entry.summary:
                highlights.append(
                    {
                        "id": entry.id,
                        "title": entry.title,
                        "type": entry.entry_type,
                        "summary": entry.summary,
                    }
                )

        return highlights[:10]  # Cap at 10 highlights

    def _format_entries_for_ai(self, entries: list[Entry]) -> str:
        """Format entries as structured text for AI summarization.

        Args:
            entries: List of Entry objects with tags loaded.

        Returns:
            Formatted string suitable for AI processing.
        """
        lines: list[str] = []

        for i, entry in enumerate(entries, 1):
            tags_str = ", ".join(tag.name for tag in entry.tags) if entry.tags else "none"
            content_preview = (entry.content or "")[:500]

            lines.append(
                f"--- Entry {i} ---\n"
                f"Type: {entry.entry_type}\n"
                f"Title: {entry.title or 'Untitled'}\n"
                f"Tags: {tags_str}\n"
                f"Content: {content_preview}\n"
            )

        return "\n".join(lines)
