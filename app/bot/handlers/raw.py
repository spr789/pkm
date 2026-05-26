"""Fallback handler for plain text messages — captures or shows help."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_entry_saved, format_help
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


@authorized_only
async def raw_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any non-command text message.

    - If in code-capture mode (after ``/code``): save as code.
    - If in note-capture mode (after ``/note``): save as note.
    - If in idea-capture mode (after ``/idea``): save as idea.
    - Otherwise: show the help reference.
    """
    text = (update.message.text or "").strip()
    if not text:
        return

    if context.user_data.get("expecting_code"):
        await _handle_code_capture(update, context)
        return

    if context.user_data.get("expecting_note"):
        context.user_data["expecting_note"] = False
        await _save_entry(update, EntryType.NOTE, text)
        return

    if context.user_data.get("expecting_idea"):
        context.user_data["expecting_idea"] = False
        await _save_entry(update, EntryType.IDEA, text)
        return

    await update.message.reply_text(format_help(), parse_mode=ParseMode.HTML)


async def _save_entry(update: Update, entry_type: EntryType, text: str) -> None:
    """Persist an entry and trigger AI enrichment."""
    from app.bot.handlers.note import _process_entry_in_background

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=entry_type,
            content=text,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )

    asyncio.create_task(_process_entry_in_background(entry.id))


async def _handle_code_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save the message as a code snippet."""
    code = update.message.text or ""
    language = context.user_data.pop("code_language", None)
    context.user_data["expecting_code"] = False

    if not code.strip():
        await update.message.reply_text("⚠️ Empty code — nothing saved.")
        return

    from app.bot.handlers.code import _save_code
    await _save_code(update, code, language)
