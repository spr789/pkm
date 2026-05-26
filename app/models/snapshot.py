"""Snapshot model for periodic AI-generated knowledge summaries."""

from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Column, Date, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SnapshotPeriod(str, enum.Enum):
    """The time period a snapshot covers."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Snapshot(TimestampMixin, Base):
    """A periodic summary of knowledge entries.

    Snapshots are AI-generated digests covering a specific time period,
    including statistics and highlighted entries.
    """

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    stats: Mapped[dict] = Column(JSONB, nullable=False, default=dict, server_default="{}")
    highlights: Mapped[dict] = Column(JSONB, nullable=False, default=dict, server_default="{}")

    def __repr__(self) -> str:
        return f"<Snapshot(id={self.id}, period={self.period}, start={self.period_start})>"
