# Contributing

Thanks for your interest in contributing to PKM.

## Getting started

1. Fork and clone the repo.
2. Create a virtual env: `python -m venv .venv && . .venv/Scripts/activate`
3. Install with dev deps: `pip install -e ".[dev]"`
4. Copy `.env.example` to `.env` and fill in the values.
5. Run migrations: `alembic upgrade head`

## Development workflow

- Run `ruff check .` and `ruff format .` before committing.
- Add tests for new features. Run `pytest` to verify.
- Keep PRs focused on a single concern. Avoid scope creep.
- Write clear commit messages following conventional commits.

## Pull request process

1. Open an issue first for non-trivial changes.
2. Create a PR from a feature branch (not `main`).
3. Ensure CI passes (lint + tests).
4. Request review from a maintainer.

## Code style

- Type hints on all public functions.
- Async/await throughout. No sync DB queries.
- Follow existing patterns in services, handlers, and models.
