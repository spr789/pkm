"""Cloud Run entry point: health-check HTTP server + Telegram bot polling."""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI

from app.bot.setup import register_handlers
from app.config import settings
from app.database import sessionmanager
from telegram.ext import Application

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, settings.log_level, logging.INFO),
)
logger = logging.getLogger(__name__)

health_app = FastAPI()


@health_app.get("/")
@health_app.get("/health")
async def health():
    return {"status": "ok"}


def build_bot_app() -> Application:
    from app.ai.router import ai_router

    async def post_init(application: Application) -> None:
        sessionmanager.init(settings.database_url)
        logger.info("Database session manager initialised")

    async def post_shutdown(application: Application) -> None:
        await ai_router.close()
        await sessionmanager.close()
        logger.info("Shutdown complete")

    app = (
        Application.builder()
        .token(settings.telegram_bot_token.get_secret_value())
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    register_handlers(app)
    return app


async def main() -> None:
    port = int(os.environ.get("PORT", "8080"))

    bot_app = build_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    logger.info("Bot started, beginning polling…")

    config = uvicorn.Config(health_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(server.serve(), bot_app.updater.start_polling())
    finally:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
