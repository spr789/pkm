"""/run command handler — LLM-powered shell command generator and execution agent."""

from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import sys
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.ai.base import ChatMessage
from app.ai.router import ai_router
from app.bot.middleware import authorized_only
from app.bot.progress import ProgressReporter

logger = logging.getLogger(__name__)

# Telegram message length limit
_TG_MAX_LEN = 4096


def _safe(text: str) -> str:
    """Escape text for safe embedding inside HTML tags."""
    return html.escape(text)


def _split_long_message(text: str, max_len: int = _TG_MAX_LEN) -> list[str]:
    """Split a long message into chunks that fit Telegram's limit."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len

        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")

    return chunks


def _extract_command(ai_text: str) -> str:
    """Extract command/code blocks from the LLM response."""
    lines = ai_text.strip().split("\n")
    code_lines = []
    in_block = False
    for line in lines:
        if line.strip().startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            code_lines.append(line)

    extracted = "\n".join(code_lines).strip()
    if not extracted:
        # Fallback if no block was found — take the whole non-empty response
        # Strip outer quotes if the LLM output raw command in quotes
        extracted = ai_text.strip().strip('"`')
    return extracted


def _is_safe_command(command: str) -> tuple[bool, str]:
    """Verify if a command is safe to execute (no service operations or destructive acts)."""
    blocklist = [
        r"\bsystemctl\b",
        r"\bservice\b",
        r"\bsc\b",
        r"\bnet\s+(start|stop|restart)\b",
        r"\bstart-service\b",
        r"\bstop-service\b",
        r"\brestart-service\b",
        r"\bkill\b",
        r"\bshutdown\b",
        r"\breboot\b",
    ]

    command_lower = command.lower()
    for pattern in blocklist:
        if re.search(pattern, command_lower):
            return False, f"Matches forbidden pattern: {pattern}"

    return True, ""


@authorized_only
async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/run <instruction>`` — translate natural language prompt to shell command and run it."""
    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        await update.message.reply_text(
            "🤖 <b>Usage:</b> /run <i>instruction in natural language</i>\n\n"
            "Example: /run list files in the current folder\n"
            "Example: /run create a folder named 'tests' and an empty python file inside it called 'test_bot.py'",
            parse_mode=ParseMode.HTML,
        )
        return

    # Typing + status message immediately
    await update.message.chat.send_action(action="typing")
    status_msg = await update.message.reply_text(
        "⏳ Preparing shell agent…",
        parse_mode=ParseMode.HTML,
    )

    chat_id = update.effective_chat.id

    try:
        from telegram import Bot
        from app.config import settings

        bot = Bot(token=settings.telegram_bot_token.get_secret_value())

        async with ProgressReporter(bot, chat_id, status_msg.message_id) as progress:
            await progress.step("🧠 Translating prompt to shell command…")

            os_name = "Windows" if sys.platform == "win32" else "Linux/macOS"
            platform_name = sys.platform

            system_instruction = (
                "You are an expert systems shell execution agent. Your job is to translate the user's natural language request "
                "into a sequence of safe shell commands to be executed on the host machine.\n\n"
                f"Operating System: {os_name} (Platform: {platform_name}).\n"
                "Generate commands compatible with this operating system's default shell (PowerShell on Windows, Bash on Linux/macOS).\n\n"
                "Constraints:\n"
                "1. Respond ONLY with the command(s) to execute enclosed in a standard markdown code block, like this:\n"
                "```\n"
                "mkdir test_folder\n"
                "```\n"
                "2. Do NOT add any conversational preamble, explanations, or commentary outside the code block.\n"
                "3. Keep commands safe, concise, and focused on the request.\n"
                "4. Do NOT attempt to start or stop system services or perform dangerous actions like full disk formatting."
            )

            messages = [
                ChatMessage(role="system", content=system_instruction),
                ChatMessage(role="user", content=prompt),
            ]

            # Generate command using our default model (OpenRouter / Gemini 2.5 Pro)
            response = await ai_router.chat_with_fallback(
                messages,
                temperature=0.0,  # Strict command generation
            )

            raw_ai = response.content.strip()
            command = _extract_command(raw_ai)

            if not command:
                await progress.finalise("❌ <b>Error:</b> AI generated an empty command.")
                return

            await progress.step("🛡 Performing safety check…")
            is_safe, reason = _is_safe_command(command)
            if not is_safe:
                await progress.finalise(
                    f"🛑 <b>Forbidden Command:</b> Execution blocked!\n"
                    f"Reason: <i>{reason}</i>\n\n"
                    f"Generated Command:\n<pre>{_safe(command)}</pre>"
                )
                return

            await progress.step(f"🚀 Executing:\n<pre>{_safe(command)}</pre>")
            start_time = time.monotonic()

            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_exec(
                    "powershell",
                    "-Command",
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "/bin/sh",
                    "-c",
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=30.0
                )
            except asyncio.TimeoutError:
                try:
                    proc.terminate()
                    await proc.wait()
                except Exception:
                    pass
                await progress.finalise("⏳ <b>Execution timed out (30s limit exceeded).</b>")
                return

            elapsed = time.monotonic() - start_time
            stdout = stdout_bytes.decode(errors="replace").strip()
            stderr = stderr_bytes.decode(errors="replace").strip()

            # Format response text
            lines = [
                f"✅ <b>Execution Complete ({elapsed:.1f}s)</b>",
                f"💻 <b>Command:</b>\n<pre>{_safe(command)}</pre>",
            ]

            if stdout:
                lines.append(f"\n📤 <b>Output:</b>\n<pre>{_safe(stdout)}</pre>")
            if stderr:
                lines.append(f"\n⚠️ <b>Error/Warning Output:</b>\n<pre>{_safe(stderr)}</pre>")
            if not stdout and not stderr:
                lines.append("\nℹ️ <i>Command completed successfully with no terminal output.</i>")

            final_text = "\n".join(lines)
            chunks = _split_long_message(final_text)

            await progress.finalise(chunks[0], parse_mode=ParseMode.HTML)
            for chunk in chunks[1:]:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                )

    except Exception as exc:
        logger.exception("Shell agent failed")
        try:
            await status_msg.edit_text(
                f"❌ <b>Shell Agent Error:</b> {_safe(str(exc))}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to send error to user")
