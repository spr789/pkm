"""Fallback handler for plain text messages (quick capture)."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_entry_saved
from app.bot.handlers.note import _process_entry_in_background
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


@authorized_only
async def raw_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any non-command text message as a quick note.

    If the user is currently in *expecting_code* mode (set by the
    ``/code`` handler) this handler yields so that
    :func:`code_message_handler` picks up the message instead.
    """
    # Defer to the code handler when in interactive code-capture mode.
    if context.user_data.get("expecting_code"):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=EntryType.NOTE,
            content=text,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )

    asyncio.create_task(_process_entry_in_background(entry.id))
