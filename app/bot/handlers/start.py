"""/start and /help command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_help
from app.bot.middleware import authorized_only

logger = logging.getLogger(__name__)


@authorized_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/start`` — welcome message with a quick overview."""
    user = update.effective_user
    name = user.first_name if user else "there"

    text = (
        f"👋 Hey <b>{name}</b>! Welcome to <b>PKM Bot</b>.\n"
        "\n"
        "I'm your personal knowledge management assistant. "
        "Capture notes, tasks, bookmarks, code snippets, ideas, "
        "and more — right from Telegram.\n"
        "\n"
        "<b>Quick start:</b>\n"
        "📝 /note <i>your thought</i> — save a note\n"
        "✅ /task <i>something to do</i> — create a task\n"
        "🔖 /bookmark <i>url</i> — save a link\n"
        "💡 /idea <i>brilliant idea</i> — capture an idea\n"
        "🔍 /search <i>query</i> — find anything\n"
        "\n"
        "Or just <b>send any message</b> — it's saved as a quick note.\n"
        "\n"
        "Type /help for the full command reference."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@authorized_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/help`` — display the full command reference."""
    await update.message.reply_text(format_help(), parse_mode=ParseMode.HTML)
