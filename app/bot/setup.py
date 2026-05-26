"""Bot setup — handler registration and error handling.

The module exposes :func:`register_handlers` which wires every command,
media, and text handler to a ``telegram.ext.Application`` instance.
``app/main.py`` calls this after building the application with its
lifecycle hooks.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# ── handler imports ─────────────────────────────────────────────────────
from app.bot.handlers.start import start_command, help_command, ping_command, unknown_command
from app.bot.handlers.note import note_command, idea_command
from app.bot.handlers.task import task_command, tasks_command, done_command
from app.bot.handlers.bookmark import bookmark_command
from app.bot.handlers.code import code_command
from app.bot.handlers.search import search_command, recent_command, tags_command
from app.bot.handlers.snapshot import snapshot_command
from app.bot.handlers.voice import voice_handler
from app.bot.handlers.media import photo_handler, document_handler
from app.bot.handlers.raw import raw_text_handler

logger = logging.getLogger(__name__)


def register_handlers(app: Application) -> None:
    """Register all command, media, and text handlers on *app*.

    **Order matters** — the plain-text catch-all (``raw_text_handler``)
    and the interactive code handler must come *after* all command
    handlers and media filters so they only match truly unstructured
    messages.
    """

    # ── command handlers ────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("idea", idea_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("bookmark", bookmark_command))
    app.add_handler(CommandHandler("code", code_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("recent", recent_command))
    app.add_handler(CommandHandler("tags", tags_command))
    app.add_handler(CommandHandler("snapshot", snapshot_command))

    # ── unknown command fallback (MUST be last command handler) ──────────
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # ── media handlers ──────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    # ── plain text handlers (MUST be last) ──────────────────────────────
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, raw_text_handler),
        group=1,
    )

    # ── error handler ───────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    logger.info("All bot handlers registered")


async def error_handler(update: object, context: object) -> None:
    """Log errors and send a user-facing message when possible."""
    from telegram.ext import ContextTypes

    ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore[assignment]
    logger.error("Unhandled exception: %s", ctx.error, exc_info=ctx.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again."
            )
        except Exception:
            logger.exception("Failed to send error message to user")
