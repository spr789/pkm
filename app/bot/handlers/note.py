"""/note and /idea command handlers."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


async def _process_entry_in_background(
    entry_id: int, chat_id: int, message_id: int
) -> None:
    """Open a fresh session and run AI processing on *entry_id*.

    This is spawned via ``asyncio.create_task`` so that the user gets an
    immediate confirmation while AI enrichment happens asynchronously.

    Uses :class:`ProgressReporter` to keep the Telegram "typing…"
    indicator alive and edit the status message in-place at each step.
    When enrichment completes, the status message is replaced with the
    clean final result.
    """
    try:
        from telegram import Bot

        from app.ai.processors import AIProcessor
        from app.ai.router import ai_router
        from app.bot.formatters import format_entry_enriched, format_entry_saved
        from app.bot.progress import ProgressReporter
        from app.config import settings

        bot = Bot(token=settings.telegram_bot_token.get_secret_value())

        async with ProgressReporter(bot, chat_id, message_id) as progress:
            await progress.step("📨 Message received — saving…")

            async with sessionmanager.session() as db:
                service = EntryService(db)
                entry = await service.get_entry(entry_id)
                if entry is None:
                    logger.warning("Background AI: entry %d not found", entry_id)
                    return

                await progress.step("🤖 AI processing started…")

                async def _on_progress(label: str) -> None:
                    await progress.step(label)

                processor = AIProcessor(ai_router)
                await processor.process_entry(
                    entry, db, progress_callback=_on_progress
                )
                logger.info("Background AI processing complete for entry %d", entry_id)

            # Re-fetch to get updated summary and tags
            async with sessionmanager.session() as db:
                service = EntryService(db)
                updated = await service.get_entry(entry_id)
                if updated and (updated.summary or updated.tags):
                    await progress.finalise(
                        format_entry_enriched(updated),
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    # No AI enrichment produced — show the plain saved card
                    entry_for_saved = updated or entry
                    await progress.finalise(
                        format_entry_saved(entry_for_saved),
                        parse_mode=ParseMode.HTML,
                    )
    except Exception:
        logger.exception("Background AI processing failed for entry %d", entry_id)


@authorized_only
async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/note <text>`` — capture a note."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        context.user_data["expecting_note"] = True
        await update.message.reply_text(
            "📝 Send me the note text now.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Send typing immediately so the user knows we're alive
    await update.message.chat.send_action(action="typing")

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=EntryType.NOTE,
            content=text,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    msg = await update.message.reply_text(
        "📨 Note received! Processing…",
        parse_mode=ParseMode.HTML,
    )

    # Fire-and-forget AI enrichment — replaces this message when done
    chat_id = update.effective_chat.id
    asyncio.create_task(_process_entry_in_background(entry.id, chat_id, msg.message_id))


@authorized_only
async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/idea <text>`` — capture an idea."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        context.user_data["expecting_idea"] = True
        await update.message.reply_text(
            "💡 Send me your brilliant idea now.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Send typing immediately
    await update.message.chat.send_action(action="typing")

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=EntryType.IDEA,
            content=text,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    msg = await update.message.reply_text(
        "💡 Idea received! Processing…",
        parse_mode=ParseMode.HTML,
    )

    chat_id = update.effective_chat.id
    asyncio.create_task(_process_entry_in_background(entry.id, chat_id, msg.message_id))
