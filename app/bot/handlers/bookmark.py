"""/bookmark command handler."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.handlers.note import _process_entry_in_background
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


@authorized_only
async def bookmark_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/bookmark <url> [description]`` — save a bookmark.

    The first argument is treated as the URL.  Everything after it becomes
    an optional description stored as the entry's content.
    """
    if not context.args:
        await update.message.reply_text(
            "🔖 <b>Usage:</b> /bookmark <i>url</i> [description]",
            parse_mode=ParseMode.HTML,
        )
        return

    url = context.args[0]
    description = " ".join(context.args[1:]) if len(context.args) > 1 else url

    # Send typing immediately
    await update.message.chat.send_action(action="typing")

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=EntryType.BOOKMARK,
            content=description,
            url=url,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    msg = await update.message.reply_text(
        "🔖 Bookmark received! Processing…",
        parse_mode=ParseMode.HTML,
    )

    chat_id = update.effective_chat.id
    asyncio.create_task(_process_entry_in_background(entry.id, chat_id, msg.message_id))
