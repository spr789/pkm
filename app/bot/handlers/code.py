"""/code command handler."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_entry_saved
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


@authorized_only
async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Extract raw text after the /code command itself.
    message_text = update.message.text or ""
    # Remove the /code prefix (may include @botname).
    after_command = ""
    if " " in message_text:
        after_command = message_text.split(None, 1)[1]

    # If nothing was provided, enter interactive "expecting_code" mode.
    if not after_command.strip():
        context.user_data["expecting_code"] = True
        context.user_data["code_language"] = None
        await update.message.reply_text(
            "💻 Send me the code snippet now.\n"
            "Optionally, first tell me the language with /code <i>language</i>.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Try to parse an optional language token on the first line.
    lines = after_command.split("\n", 1)
    first_line_tokens = lines[0].strip().split()

    if len(lines) > 1:
        # Multi-line: first token of first line is language, rest + remaining lines = code
        language = first_line_tokens[0] if first_line_tokens else None
        remaining_first = " ".join(first_line_tokens[1:]) if len(first_line_tokens) > 1 else ""
        code_content = (remaining_first + "\n" + lines[1]).strip() if remaining_first else lines[1].strip()
    elif len(first_line_tokens) > 1:
        # Single line with multiple tokens: first token = language, rest = code
        language = first_line_tokens[0]
        code_content = " ".join(first_line_tokens[1:])
    else:
        # Single token — could be either a language or a snippet.
        # If it looks like a known short language name treat it as language
        # and enter interactive mode.  Otherwise save it as code.
        token = first_line_tokens[0]
        known_langs = {
            "python", "py", "javascript", "js", "typescript", "ts",
            "java", "go", "rust", "c", "cpp", "csharp", "cs", "ruby",
            "rb", "php", "swift", "kotlin", "sql", "bash", "sh",
            "html", "css", "json", "yaml", "yml", "toml", "xml",
            "lua", "r", "scala", "perl", "elixir", "haskell",
        }
        if token.lower() in known_langs:
            context.user_data["expecting_code"] = True
            context.user_data["code_language"] = token.lower()
            await update.message.reply_text(
                f"💻 Language set to <code>{token.lower()}</code>.\n"
                "Now send me the code snippet.",
                parse_mode=ParseMode.HTML,
            )
            return
        else:
            language = None
            code_content = token

    await _save_code(update, code_content, language)


async def _save_code(update: Update, code: str, language: str | None) -> None:
    """Persist a code snippet as an Entry."""
    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=EntryType.CODE,
            content=code,
            language=language,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )
