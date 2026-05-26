"""/provider and /model commands for AI configuration."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.ai.override import get_model, get_provider, set_model, set_provider
from app.ai.router import FALLBACK_CHAIN, ai_router
from app.bot.middleware import authorized_only

logger = logging.getLogger(__name__)


@authorized_only
async def provider_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show or switch the active AI provider."""
    args = context.args
    text = (update.message.text or "").strip()

    if not args and len(text.split()) < 2:
        current = get_provider() or "gemini (default)"
        parts = [
            f"🔌 <b>Current provider:</b> {current}\n",
            "<b>Available providers:</b>",
        ]
        for name in FALLBACK_CHAIN:
            try:
                ai_router.get_provider(name)
                label = f" ✅ {name}" if name == (get_provider() or "gemini") else f" {name}"
                parts.append(label)
            except Exception:
                pass
        parts.append("\nUsage: /provider &lt;name&gt;")
        await update.message.reply_text("\n".join(parts), parse_mode=ParseMode.HTML)
        return

    name = args[0].lower()
    try:
        ai_router.get_provider(name)
    except Exception:
        await update.message.reply_text(
            f"❌ Provider '{name}' is not available (no API key configured).",
            parse_mode=ParseMode.HTML,
        )
        return

    set_provider(name)
    await update.message.reply_text(
        f"✅ Switched to <b>{name}</b>", parse_mode=ParseMode.HTML,
    )


@authorized_only
async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show or switch the AI model."""
    args = context.args
    text = (update.message.text or "").strip()

    if not args and len(text.split()) < 2:
        current = get_model() or "provider default"
        await update.message.reply_text(
            f"🧠 <b>Current model:</b> {current}\n\n"
            "Usage: /model &lt;model-name&gt;\n"
            "Example: /model gemini-2.5-flash\n\n"
            "Note: The model must be supported by your active provider.",
            parse_mode=ParseMode.HTML,
        )
        return

    set_model(args[0])
    await update.message.reply_text(
        f"✅ Model set to <b>{args[0]}</b>", parse_mode=ParseMode.HTML,
    )
