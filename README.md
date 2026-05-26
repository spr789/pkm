# PKM — Personal Knowledge Manager

A **Telegram-first** knowledge management system to capture, organize, search, and retrieve notes, tasks, bookmarks, code snippets, ideas, voice memos, photos, and documents — all through a Telegram bot.

## Features

- **Capture anything** — notes, ideas, tasks, bookmarks, code snippets, voice messages, photos, documents
- **Full-text search** — PostgreSQL `tsvector`/`tsquery` across all entries
- **Tagging** — auto-extracted (AI) and manual tags with many-to-many relationships
- **Task management** — create, list, and complete tasks with TODO/IN_PROGRESS/DONE status
- **AI enrichment** — automatic summarization and tag extraction via configurable LLM providers
- **Knowledge snapshots** — daily/weekly/monthly AI-generated summaries of your knowledge base
- **Multi-provider AI** — OpenRouter, OpenAI, Anthropic, Gemini with automatic fallback
- **User authorization** — Telegram user ID allow-list

## Quick start

### Prerequisites

- Python 3.12+
- PostgreSQL
- Telegram bot token (from [@BotFather](https://t.me/BotFather))

### Setup

```bash
# Clone and enter the project
cd pkm

# Create virtual environment
python -m venv .venv

# Activate it
source .venv/Scripts/activate   # Git Bash
.venv\Scripts\activate          # cmd / PowerShell

# Install dependencies
pip install -e ".[dev,ai]"

# Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS

# Create the database
python create_db.py

# Run migrations
alembic upgrade head

# Start the bot
python -m app.main
```

## Configuration

All settings are via `.env` file (see `.env.example`):

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async connection string |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs (empty = open) |
| `OPENROUTER_API_KEY` | OpenRouter API key (default provider) |
| `OPENAI_API_KEY` | OpenAI API key (fallback) |
| `ANTHROPIC_API_KEY` | Anthropic API key (fallback) |
| `GOOGLE_API_KEY` | Google Gemini API key (fallback) |
| `AI_DEFAULT_PROVIDER` | Default AI provider (default: `openrouter`) |
| `AI_DEFAULT_MODEL` | Default AI model (default: `deepseek/deepseek-chat-v3-0324:free`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |

## Bot commands

| Command | Description |
|---|---|
| `/start` | Welcome message with quick-start guide |
| `/help` | Full command reference |
| `/note <text>` | Save a quick note |
| `/idea <text>` | Capture an idea |
| `/task <text>` | Create a TODO task |
| `/tasks` | List open tasks |
| `/done <id>` | Mark a task as completed |
| `/bookmark <url> [desc]` | Save a bookmark |
| `/code [lang] <code>` | Save a code snippet |
| `/search <query>` | Full-text search |
| `/recent [n]` | Show last N entries (max 50) |
| `/tags` | List all tags with entry counts |
| `/snapshot [daily\|weekly\|monthly] [new]` | Generate/retrieve knowledge snapshot |

**Media:** Voice messages, photos, and documents are saved automatically.

## Project structure

```
pkm/
├── app/
│   ├── main.py              # Application entry point
│   ├── config.py            # Pydantic settings from .env
│   ├── database.py          # Async SQLAlchemy session manager
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic (entries, tags, search, snapshots)
│   ├── bot/
│   │   ├── handlers/        # Command and message handlers
│   │   ├── setup.py         # Handler registration
│   │   ├── middleware.py    # Authorization decorator
│   │   └── formatters.py    # HTML message formatting
│   └── ai/
│       ├── base.py          # Abstract provider + types
│       ├── router.py        # Provider routing with fallback
│       ├── processors.py    # Entry processing pipeline
│       └── providers/       # OpenRouter, OpenAI, Anthropic, Gemini
├── alembic/                 # Database migrations
├── .env / .env.example      # Configuration
├── pyproject.toml           # Package metadata & dependencies
└── create_db.py             # Database creation utility
```

## Development

```bash
# Lint
ruff check .

# Format
ruff format .

# Auto-fix
ruff check --fix .

# Test
pytest

# Create a migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## AI fallback chain

If the primary AI provider fails (rate limit, unavailable), the system automatically tries the next provider in this order:

1. **OpenRouter** → 2. **OpenAI** → 3. **Anthropic** → 4. **Google Gemini**

Only providers with configured API keys are attempted.
