"""Real-time progress feedback utilities for Telegram bot handlers.

Provides :class:`ProgressReporter` — a context-manager that keeps the
Telegram "typing…" indicator alive and edits a single status message
in-place as each processing step completes.  When the reporter is
finalised, the interim status message is replaced with the clean result.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from telegram import Bot
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# How often to resend the "typing…" chat action (Telegram expires it ~5 s)
_TYPING_INTERVAL_S = 4.0


class ProgressReporter:
    """Live progress reporter for long-running bot operations.

    Usage::

        async with ProgressReporter(bot, chat_id, status_msg_id) as progress:
            await progress.step("📨 Message received")
            await progress.step("🧠 Summarising with AI…")
            ...
        # After the context manager exits, the typing-loop stops.
        # Call progress.finalise(text) to replace the status msg with the result.

    The "typing…" chat action is sent on a background loop so the user
    always sees the bot is alive.  Each :meth:`step` call edits the
    status message with a nice progress bar showing completed and
    pending steps.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        status_message_id: int,
        *,
        steps: Sequence[str] | None = None,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._msg_id = status_message_id
        self._typing_task: asyncio.Task | None = None
        self._completed_steps: list[str] = []
        self._planned_steps: list[str] = list(steps) if steps else []
        self._current_step: str | None = None
        self._last_text: str | None = None

    # ── context manager ─────────────────────────────────────────────

    async def __aenter__(self) -> ProgressReporter:
        self._typing_task = asyncio.create_task(self._typing_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        if self._typing_task and not self._typing_task.done():
            self._typing_task.cancel()
            try:
                await self._typing_task
            except asyncio.CancelledError:
                pass
        return None

    # ── public API ──────────────────────────────────────────────────

    async def step(self, label: str) -> None:
        """Mark the current step and update the status message."""
        if self._current_step:
            self._completed_steps.append(self._current_step)
        self._current_step = label
        await self._update_status()

    async def finalise(self, final_text: str, parse_mode: str = ParseMode.HTML) -> None:
        """Replace the status message with the final clean result."""
        # Stop typing
        if self._typing_task and not self._typing_task.done():
            self._typing_task.cancel()
            try:
                await self._typing_task
            except asyncio.CancelledError:
                pass

        try:
            await self._bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=self._msg_id,
                text=final_text,
                parse_mode=parse_mode,
            )
        except TelegramError:
            logger.exception("Failed to send final message")

    # ── internal ────────────────────────────────────────────────────

    async def _typing_loop(self) -> None:
        """Continuously send 'typing' chat action until cancelled."""
        try:
            while True:
                try:
                    await self._bot.send_chat_action(
                        chat_id=self._chat_id,
                        action=ChatAction.TYPING,
                    )
                except TelegramError:
                    logger.debug("Failed to send typing action")
                await asyncio.sleep(_TYPING_INTERVAL_S)
        except asyncio.CancelledError:
            return

    async def _update_status(self) -> None:
        """Edit the status message to show current progress."""
        lines: list[str] = []

        for done_step in self._completed_steps:
            lines.append(f"✅ {done_step}")

        if self._current_step:
            lines.append(f"⏳ {self._current_step}")

        # Show remaining planned steps (if known) as pending
        done_and_current = set(self._completed_steps)
        if self._current_step:
            done_and_current.add(self._current_step)
        for planned in self._planned_steps:
            if planned not in done_and_current:
                lines.append(f"⬜ {planned}")

        text = "\n".join(lines)

        # Avoid editing if text hasn't changed (Telegram returns error)
        if text == self._last_text:
            return
        self._last_text = text

        try:
            await self._bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=self._msg_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            logger.debug("Failed to update progress message")


async def send_typing(bot: Bot, chat_id: int) -> None:
    """Send a one-shot 'typing' chat action (fire-and-forget helper)."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except TelegramError:
        pass
