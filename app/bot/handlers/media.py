"""Photo and document message handlers."""

from __future__ import annotations

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
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photos.

    The largest available resolution is selected.  The caption (if any)
    is stored as the entry content; otherwise a placeholder is used.
    """
    photos = update.message.photo
    if not photos:
        return

    # Telegram sends several sizes — pick the largest.
    photo = photos[-1]
    caption = update.message.caption or "[Photo]"

    async with sessionmanager.session() as db:
        entry_svc = EntryService(db)
        entry = await entry_svc.create_entry(
            entry_type=EntryType.MEMORY,
            content=caption,
            source="telegram",
            source_message_id=update.message.message_id,
        )

        attach_svc = AttachmentService(db)
        await attach_svc.create_attachment(
            entry_id=entry.id,
            file_type="image",
            telegram_file_id=photo.file_id,
            file_name=f"photo_{entry.id}.jpg",
            mime_type="image/jpeg",
            file_size=photo.file_size,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )
    logger.info("Photo saved as entry %d", entry.id)


@authorized_only
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming document files.

    The file name is used as the entry title.  If a caption is provided
    it becomes the content; otherwise a placeholder is used.
    """
    doc = update.message.document
    if doc is None:
        return

    file_name = doc.file_name or "untitled"
    caption = update.message.caption or f"[Document: {file_name}]"

    async with sessionmanager.session() as db:
        entry_svc = EntryService(db)
        entry = await entry_svc.create_entry(
            entry_type=EntryType.DOCUMENT,
            content=caption,
            title=file_name,
            source="telegram",
            source_message_id=update.message.message_id,
        )

        attach_svc = AttachmentService(db)
        await attach_svc.create_attachment(
            entry_id=entry.id,
            file_type="document",
            telegram_file_id=doc.file_id,
            file_name=file_name,
            mime_type=doc.mime_type,
            file_size=doc.file_size,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )
    logger.info("Document '%s' saved as entry %d", file_name, entry.id)
