"""Fallback handler for plain text messages — shows help."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_help
from app.bot.middleware import authorized_only

logger = logging.getLogger(__name__)


@authorized_only
async def raw_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any non-command text message — show the help reference.

    Use ``/note <text>`` or other commands to save content.
    """
    if context.user_data.get("expecting_code"):
        return

    await update.message.reply_text(format_help(), parse_mode=ParseMode.HTML)
