"""Pydantic schemas for Entry CRUD operations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TagResponse(BaseModel):
    """Tag data returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str | None = None
    color: str | None = None


class EntryCreate(BaseModel):
    """Schema for creating a new Entry."""

    entry_type: str
    content: str
    title: str | None = None
    url: str | None = None
    language: str | None = None
    task_status: str | None = None
    task_due_date: datetime | None = None
    tags: list[str] | None = None
    source: str = "telegram"
    source_message_id: int | None = None
    metadata_: dict | None = Field(default=None, alias="metadata")


class EntryUpdate(BaseModel):
    """Schema for partially updating an Entry. All fields are optional."""

    entry_type: str | None = None
    content: str | None = None
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    language: str | None = None
    task_status: str | None = None
    task_due_date: datetime | None = None
    is_pinned: bool | None = None
    is_archived: bool | None = None
    tags: list[str] | None = None
    metadata_: dict | None = Field(default=None, alias="metadata")


class EntryResponse(BaseModel):
    """Full Entry data returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_type: str
    title: str | None = None
    content: str
    summary: str | None = None
    source: str
    source_message_id: int | None = None
    task_status: str | None = None
    task_due_date: datetime | None = None
    url: str | None = None
    language: str | None = None
    is_pinned: bool
    is_archived: bool
    tags: list[TagResponse] = []
    created_at: datetime
    updated_at: datetime | None = None


class EntryListResponse(BaseModel):
    """Paginated list of entries."""

    items: list[EntryResponse]
    total: int
