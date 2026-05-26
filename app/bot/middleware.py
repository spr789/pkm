"""Authentication middleware for Telegram bot handlers.

Provides the ``authorized_only`` decorator that restricts handler access
to user IDs listed in ``settings.allowed_user_id_list``.  When the list
is empty every user is allowed (convenient during initial setup).
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Coroutine

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings

logger = logging.getLogger(__name__)


def authorized_only(
    func: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Decorator that restricts a handler to authorised Telegram users.

    If ``settings.allowed_user_id_list`` is empty, **all** users are
    permitted (useful for first-time setup).  Otherwise only user IDs
    present in the list may invoke the handler.

    Unauthorised attempts are logged and the user receives a short
    rejection message.
    """

    @functools.wraps(func)
    async def wrapper(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        user = update.effective_user
        if user is None:
            logger.warning("Received update without effective_user – ignoring.")
            return

        allowed_ids: list[int] = settings.allowed_user_id_list

        # If the allow-list is empty we let everyone through (initial setup).
        if allowed_ids and user.id not in allowed_ids:
            logger.warning(
                "Unauthorised access attempt by user %s (id=%d)",
                user.username or user.full_name,
                user.id,
            )
            if update.effective_message:
                await update.effective_message.reply_text("⛔ Unauthorized")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
