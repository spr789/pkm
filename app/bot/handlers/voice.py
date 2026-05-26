"""Voice message handler."""

from __future__ import annotations

import io
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_entry_saved
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType
from app.services.attachment_service import AttachmentService
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


@authorized_only
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages.

    Downloads the voice file into memory, creates an Entry with type
    VOICE, and attaches the Telegram file reference.  Transcription via
    Whisper can be added in a future iteration.
    """
    voice = update.message.voice
    if voice is None:
        return

    # Download voice data (kept in memory for potential future processing).
    voice_file = await voice.get_file()
    buffer = io.BytesIO()
    await voice_file.download_to_memory(out=buffer)
    buffer.seek(0)

    duration = voice.duration or 0

    async with sessionmanager.session() as db:
        entry_svc = EntryService(db)
        entry = await entry_svc.create_entry(
            entry_type=EntryType.VOICE,
            content="[Voice message - transcription pending]",
            source="telegram",
            source_message_id=update.message.message_id,
            metadata={"duration_seconds": duration},
        )

        attach_svc = AttachmentService(db)
        await attach_svc.create_attachment(
            entry_id=entry.id,
            file_type="audio",
            telegram_file_id=voice.file_id,
            file_name=f"voice_{entry.id}.ogg",
            mime_type=voice.mime_type or "audio/ogg",
            file_size=voice.file_size,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )
    logger.info("Voice message saved as entry %d (%ds)", entry.id, duration)
