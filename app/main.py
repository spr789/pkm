"""Main entry point for the PKM Telegram bot (polling mode).

Run with::

    python -m app.main
"""

from __future__ import annotations

import logging

from telegram.ext import Application

from app.config import settings
from app.database import sessionmanager

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, settings.log_level, logging.INFO),
)
logger = logging.getLogger(__name__)


# ── lifecycle callbacks ─────────────────────────────────────────────────


async def post_init(application: Application) -> None:
    """Called after ``Application.initialize()`` — sets up shared resources."""
    sessionmanager.init(settings.database_url)
    logger.info("Database session manager initialised")


async def post_shutdown(application: Application) -> None:
    """Called after ``Application.shutdown()`` — tears down shared resources."""
    try:
        from app.ai.router import ai_router

        await ai_router.close()
        logger.info("AI router closed")
    except Exception:
        logger.debug("AI router close skipped (not initialised or unavailable)")

    await sessionmanager.close()
    logger.info("Database session manager closed — shutdown complete")


# ── main ────────────────────────────────────────────────────────────────


def main() -> None:
    """Build the bot application with lifecycle hooks and start polling."""
    from app.bot.setup import register_handlers

    app = (
        Application.builder()
        .token(settings.telegram_bot_token.get_secret_value())
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    register_handlers(app)

    logger.info("Starting PKM bot in polling mode…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
