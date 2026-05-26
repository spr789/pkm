"""/task, /tasks, and /done command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_entry_saved, format_task_list
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.entry import EntryType, TaskStatus
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


@authorized_only
async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/task <text>`` — create a to-do item."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "✅ <b>Usage:</b> /task <i>something to do</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.create_entry(
            entry_type=EntryType.TASK,
            content=text,
            task_status=TaskStatus.TODO,
            source="telegram",
            source_message_id=update.message.message_id,
        )

    await update.message.reply_text(
        format_entry_saved(entry), parse_mode=ParseMode.HTML,
    )


@authorized_only
async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/tasks`` — list open tasks (TODO + IN_PROGRESS)."""
    async with sessionmanager.session() as db:
        service = EntryService(db)
        todo = await service.get_tasks(status=TaskStatus.TODO)
        in_progress = await service.get_tasks(status=TaskStatus.IN_PROGRESS)

    all_tasks = list(todo) + list(in_progress)

    await update.message.reply_text(
        format_task_list(all_tasks), parse_mode=ParseMode.HTML,
    )


@authorized_only
async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/done <id>`` — mark a task as completed."""
    if not context.args:
        await update.message.reply_text(
            "✅ <b>Usage:</b> /done <i>task_id</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_id = context.args[0].lstrip("#")
    try:
        entry_id = int(raw_id)
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please provide a valid numeric task ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    async with sessionmanager.session() as db:
        service = EntryService(db)
        entry = await service.complete_task(entry_id)

    if entry is None:
        await update.message.reply_text(
            f"⚠️ Task <code>#{entry_id}</code> not found or already completed.",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        f"✅ Task <code>#{entry.id}</code> marked as <b>done</b>!",
        parse_mode=ParseMode.HTML,
    )
