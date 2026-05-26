"""AI layer for PKM system.

Provides an abstraction over multiple AI providers (OpenRouter, OpenAI,
Anthropic, Google Gemini) with automatic fallback, retry logic, and
content processing pipelines for summarization, tag extraction, and
snapshot generation.
"""

from __future__ import annotations
