"""/note and /idea command handlers."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_entry_saved
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


async def _process_entry_in_background(entry_id: int) -> None:
    """Open a fresh session and run AI processing on *entry_id*.

    This is spawned via ``asyncio.create_task`` so that the user gets an
    immediate confirmation while AI enrichment happens asynchronously.
    """
    try:
        from app.ai.router import ai_router
        from app.ai.processors import AIProcessor

        async with sessionmanager.session() as db:
            service = EntryService(db)
            entry = await service.get_entry(entry_id)
            if entry is None:
                logger.warning("Background AI: entry %d not found", entry_id)
                return

            processor = AIProcessor(ai_router)
            await processor.process_entry(entry, db)
            logger.info("Background AI processing complete for entry %d", entry_id)
    except Exception:
        logger.exception("Background AI processing failed for entry %d", entry_id)


@authorized_only
async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/note <text>`` — capture a note."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "📝 <b>Usage:</b> /note <i>your text here</i>",
            parse_mode=ParseMode.HTML,
        )
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

    # Fire-and-forget AI enrichment
    asyncio.create_task(_process_entry_in_background(entry.id))


@authorized_only
async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/idea <text>`` — capture an idea."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "💡 <b>Usage:</b> /idea <i>your brilliant idea</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=EntryType.IDEA,
            content=text,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )

    asyncio.create_task(_process_entry_in_background(entry.id))
