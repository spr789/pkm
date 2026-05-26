"""/start and /help command handlers."""

from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.ai.base import ChatMessage
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


@authorized_only
async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test the AI provider — ping OpenCode and report status."""
    from app.ai.router import ai_router

    msg = await update.message.reply_text("⏳ Pinging AI provider…")

    try:
        start = time.monotonic()
        response = await ai_router.chat_with_fallback(
            [ChatMessage(role="user", content="Say exactly: 'pong'. Nothing else.")],
            temperature=0.1,
            max_tokens=10,
        )
        elapsed = time.monotonic() - start

        parts = [
            "✅ AI is responding",
            f"Model: <code>{response.model}</code>",
            f"Provider: <code>{response.provider}</code>",
            f"Time: {elapsed:.1f}s",
        ]
        if response.reasoning:
            parts.append(f"\n🧠 <b>Reasoning:</b>\n<pre>{response.reasoning[:500]}</pre>")
        parts.append(f"\n💬 <b>Response:</b> {response.content}")

        await msg.edit_text("\n".join(parts), parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ AI ping failed:\n<code>{e}</code>", parse_mode=ParseMode.HTML)


@authorized_only
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unrecognised commands — show help."""
    await update.message.reply_text(
        f"❌ Unknown command. Here's what I can do:\n\n{format_help()}",
        parse_mode=ParseMode.HTML,
    )
