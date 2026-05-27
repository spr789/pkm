"""/ask command handler — direct AI prompting with live progress."""

from __future__ import annotations

import html
import logging
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.ai.base import ChatMessage
from app.bot.middleware import authorized_only
from app.bot.progress import ProgressReporter

logger = logging.getLogger(__name__)

# Telegram message length limit
_TG_MAX_LEN = 4096


def _safe(text: str) -> str:
    """Escape text for safe embedding inside HTML tags."""
    return html.escape(text)


def _split_long_message(text: str, max_len: int = _TG_MAX_LEN) -> list[str]:
    """Split a long message into chunks that fit Telegram's limit.

    Tries to split on paragraph boundaries, then line boundaries,
    then hard-cuts at max_len.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        # Try to find a paragraph break
        cut = remaining.rfind("\n\n", 0, max_len)
        if cut == -1:
            # Try a line break
            cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            # Hard cut
            cut = max_len

        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")

    return chunks


def _format_streaming_message(
    reasoning_parts: list[str],
    content_parts: list[str],
    provider: str,
    model: str,
    elapsed: float | None = None,
    is_final: bool = False,
) -> str:
    """Format the streaming content and reasoning into a nice HTML string."""
    reasoning = "".join(reasoning_parts).strip()
    content = "".join(content_parts).strip()

    parts: list[str] = []

    # Format reasoning
    if reasoning:
        if not is_final:
            # During live streaming, show reasoning as "Reasoning..."
            # Keep it under 1000 characters to be safe
            reasoning_preview = reasoning
            if len(reasoning_preview) > 1000:
                reasoning_preview = "…" + reasoning_preview[-1000:]
            parts.append(
                f"🧠 <b>Reasoning...</b>\n<pre>{_safe(reasoning_preview)}</pre>\n"
            )
        else:
            # Final output has reasoning in a block (truncated if extremely long)
            reasoning_preview = reasoning[:1200]
            if len(reasoning) > 1200:
                reasoning_preview += "…"
            parts.append(
                f"🧠 <b>Reasoning:</b>\n<pre>{_safe(reasoning_preview)}</pre>\n"
            )

    # Format content
    if content:
        if not is_final:
            parts.append(f"✨ <b>Answer...</b>\n{_safe(content)}")
        else:
            parts.append(f"{_safe(content)}")
    elif not reasoning:
        # Initial status
        parts.append("⏳ AI is thinking…")
    else:
        # Has reasoning but no content yet
        if not is_final:
            parts.append("⏳ Generating answer next…")

    # Add footer on final
    if is_final and provider and model:
        elapsed_str = f" • {elapsed:.1f}s" if elapsed is not None else ""
        parts.append(
            f"\n\n<i>⚡ {provider}/{model}{elapsed_str}</i>"
        )

    return "\n".join(parts)


@authorized_only
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/ask <question>`` — ask the AI anything, with live progress.

    The bot shows typing + progress steps while the AI is thinking,
    then delivers the final answer. Supports multi-turn context: reply
    to a previous bot answer with ``/ask <follow-up>`` to continue the
    conversation.
    """
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text(
            "🤖 <b>Usage:</b> /ask <i>your question</i>\n\n"
            "Example: /ask What is the capital of France?\n"
            "Example: /ask Explain async/await in Python",
            parse_mode=ParseMode.HTML,
        )
        return

    # Typing + status message immediately
    await update.message.chat.send_action(action="typing")
    status_msg = await update.message.reply_text(
        "⏳ Thinking…",
        parse_mode=ParseMode.HTML,
    )

    chat_id = update.effective_chat.id

    try:
        from telegram import Bot

        from app.ai.router import ai_router
        from app.config import settings

        bot = Bot(token=settings.telegram_bot_token.get_secret_value())

        async with ProgressReporter(bot, chat_id, status_msg.message_id) as progress:
            await progress.step("📨 Question received")

            # Build message list — optionally include conversation context
            messages = _build_messages(question, update, context)

            await progress.step("🧠 AI stream starting…")
            start = time.monotonic()

            reasoning_accumulated: list[str] = []
            content_accumulated: list[str] = []
            last_edit_time = time.monotonic()
            edit_interval = 1.5
            active_provider = ""
            active_model = ""

            stream = ai_router.stream_chat_with_fallback(
                messages,
                temperature=0.7,
                max_tokens=4096,
            )

            async for chunk in stream:
                if chunk.provider:
                    active_provider = chunk.provider
                if chunk.model:
                    active_model = chunk.model

                if chunk.reasoning:
                    reasoning_accumulated.append(chunk.reasoning)
                if chunk.content:
                    content_accumulated.append(chunk.content)

                # Throttle edits to avoid Telegram rate limits
                now = time.monotonic()
                if now - last_edit_time >= edit_interval:
                    interim_text = _format_streaming_message(
                        reasoning_accumulated,
                        content_accumulated,
                        active_provider,
                        active_model,
                        is_final=False,
                    )
                    if interim_text:
                        try:
                            await bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_msg.message_id,
                                text=interim_text,
                                parse_mode=ParseMode.HTML,
                            )
                            last_edit_time = now
                        except Exception:
                            # Skip if edit fails (e.g. rate-limit or identical content)
                            pass

            # Finalize response
            elapsed = time.monotonic() - start
            answer_final = "".join(content_accumulated).strip()

            # Store in conversation context for follow-ups
            _store_context(context, question, answer_final)

            # Build the final message
            final_text = _format_streaming_message(
                reasoning_accumulated,
                content_accumulated,
                active_provider,
                active_model,
                elapsed=elapsed,
                is_final=True,
            )

            # Handle long responses — split if needed
            chunks = _split_long_message(final_text)
            await progress.finalise(chunks[0], parse_mode=ParseMode.HTML)

            # Send remaining chunks as new messages
            for chunk in chunks[1:]:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                )

    except Exception as exc:
        logger.exception("AI ask failed")
        try:
            await status_msg.edit_text(
                f"❌ <b>AI error:</b> {_safe(str(exc))}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to send error to user")


def _build_messages(
    question: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> list[ChatMessage]:
    """Build the ChatMessage list with system prompt and optional context.

    If the user's message is a reply to a previous bot answer, or if
    there's a recent conversation stored in user_data, include that
    as context for multi-turn.
    """
    system = ChatMessage(
        role="system",
        content=(
            "You are a helpful, concise AI assistant embedded in a personal "
            "knowledge management Telegram bot. "
            "Answer clearly and directly. Use bullet points and short "
            "paragraphs for readability. "
            "If code is involved, provide working examples. "
            "Do NOT use markdown formatting (no **, ##, etc.) — use plain text. "
            "Keep responses focused and under 2000 characters when possible."
        ),
    )

    messages: list[ChatMessage] = [system]

    # Include recent conversation history (last 3 turns) for context
    history: list[dict] = context.user_data.get("ask_history", [])
    for turn in history[-3:]:
        messages.append(ChatMessage(role="user", content=turn["q"]))
        messages.append(ChatMessage(role="assistant", content=turn["a"]))

    # Include the quoted message if replying to one
    reply = update.message.reply_to_message
    if reply and reply.text and not history:
        messages.append(
            ChatMessage(
                role="assistant",
                content=f"[Previous message]: {reply.text[:2000]}",
            )
        )

    messages.append(ChatMessage(role="user", content=question))
    return messages


def _store_context(
    context: ContextTypes.DEFAULT_TYPE,
    question: str,
    answer: str,
) -> None:
    """Store the Q/A pair in user_data for multi-turn follow-ups.

    Keeps the last 5 turns to avoid unbounded memory growth.
    """
    history: list[dict] = context.user_data.setdefault("ask_history", [])
    history.append({"q": question, "a": answer})
    # Keep only last 5 turns
    if len(history) > 5:
        context.user_data["ask_history"] = history[-5:]
