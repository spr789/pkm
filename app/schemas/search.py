"""Pydantic schemas for full-text search operations."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.entry import EntryResponse


class SearchRequest(BaseModel):
    """Parameters for searching entries."""

    query: str
    entry_type: str | None = None
    tags: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResult(BaseModel):
    """A single search result with relevance ranking."""

    entry: EntryResponse
    rank: float
    headline: str | None = None


class SearchResponse(BaseModel):
    """Paginated search results."""

    results: list[SearchResult]
    total: int
    query: str
