# CLAUDE.md — PKM Project Guide

## Project Overview

PKM is a Telegram-first personal knowledge management system. Built with Python 3.12+, async SQLAlchemy, PostgreSQL, and python-telegram-bot. Entries (notes, tasks, bookmarks, code, voice, photos, docs) are saved via bot commands and enriched by AI (summarization, tag extraction, snapshots) through a multi-provider router with automatic fallback (OpenRouter → OpenAI → Anthropic → Gemini).

## Commands

- Run bot: `python -m app.main`
- Lint: `ruff check .`
- Format: `ruff format .`
- Test: `pytest`
- Migrate: `alembic upgrade head`
- Create migration: `alembic revision --autogenerate -m "desc"`
- Activate venv: `. .venv/Scripts/activate`

## Code Conventions

- Async/await throughout; SQLAlchemy async sessions
- Type hints on all public functions
- Pydantic v2 for settings (`BaseSettings`) and schemas
- Services accept `AsyncSession` as first constructor arg
- Bot handlers decorated with `@authorized_only`
- AI providers extend `AIProvider` ABC, registered in `router.py`
- Alembic migrations with `render_as_batch=True`

## Karpathy's Behavioral Guidelines

These four principles apply to all AI-assisted work on this codebase:

### 1. Think Before Coding

- State assumptions explicitly before implementing. Ask if uncertain.
- Present multiple interpretations when ambiguity exists.
- If a simpler approach exists, say so and push back.
- Stop when confused. Name what's unclear and ask.

### 2. Simplicity First

- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked. No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- If 200 lines could be 50, rewrite it.

### 3. Surgical Changes

- Touch only what you must. Clean up only your own mess.
- Don't improve adjacent code, comments, or formatting.
- Don't refactor things that aren't broken. Match existing style.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that *your changes* made unused.

### 4. Goal-Driven Execution

- Transform imperative tasks into verifiable goals.
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- For multi-step tasks, state a brief plan with verification checkpoints.

**Signs it's working:** fewer unnecessary changes in diffs, fewer rewrites, clarifying questions come before implementation.
