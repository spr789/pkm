"""/search, /recent, and /tags command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import (
    format_entry,
    format_search_results,
    format_tag_list,
)
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.services.entry_service import EntryService
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)


@authorized_only
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/search <query>`` — full-text search across all entries."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "🔍 <b>Usage:</b> /search <i>query</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    async with sessionmanager.session() as db:
        search_svc = SearchService(db)
        results, total = await search_svc.full_text_search(query, limit=20)

    text = format_search_results(results, query)
    if total > 20:
        text += f"\n\n<i>Showing 20 of {total} results.</i>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@authorized_only
async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/recent [n]`` — show the *n* most recent entries."""
    limit = 10
    if context.args:
        try:
            limit = max(1, min(int(context.args[0]), 50))
        except ValueError:
            pass

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entries = await service.get_recent(limit=limit)

    if not entries:
        await update.message.reply_text("📭 No entries yet. Start capturing!")
        return

    lines = [f"📋 <b>Recent entries</b> (last {len(entries)}):\n"]
    for entry in entries:
        lines.append(format_entry(entry))
        lines.append("")  # blank separator

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
    )


@authorized_only
async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/tags`` — list all tags with entry counts."""
    async with sessionmanager.session() as db:
        search_svc = SearchService(db)
        tags = await search_svc.get_tags_with_counts()

    await update.message.reply_text(
        format_tag_list(tags), parse_mode=ParseMode.HTML,
    )
