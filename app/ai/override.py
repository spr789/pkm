"""In-memory overrides for AI provider and model selection."""

from __future__ import annotations

_provider: str | None = None
_model: str | None = None


def set_provider(name: str | None) -> None:
    global _provider
    _provider = name


def set_model(name: str | None) -> None:
    global _model
    _model = name


def get_provider() -> str | None:
    return _provider


def get_model() -> str | None:
    return _model
