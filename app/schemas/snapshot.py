"""Pydantic schemas for Snapshot operations."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class SnapshotResponse(BaseModel):
    """Full Snapshot data returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    period: str
    period_start: date
    period_end: date
    summary: str
    stats: dict
    highlights: dict
    created_at: datetime


class SnapshotListResponse(BaseModel):
    """Paginated list of snapshots."""

    items: list[SnapshotResponse]
    total: int
