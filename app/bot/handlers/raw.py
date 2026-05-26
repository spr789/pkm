"""Fallback handler for plain text messages — shows help or captures code."""

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
    """Handle any non-command text message.

    - If in code-capture mode (after ``/code``): save as code snippet.
    - Otherwise: show the help reference.
    """
    if context.user_data.get("expecting_code"):
        await _handle_code_capture(update, context)
        return

    await update.message.reply_text(format_help(), parse_mode=ParseMode.HTML)


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
