"""/snapshot command handler."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import format_snapshot
from app.bot.middleware import authorized_only
from app.database import sessionmanager
from app.models.snapshot import SnapshotPeriod
from app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)

_PERIOD_MAP: dict[str, SnapshotPeriod] = {
    "daily": SnapshotPeriod.DAILY,
    "weekly": SnapshotPeriod.WEEKLY,
    "monthly": SnapshotPeriod.MONTHLY,
}


@authorized_only
async def snapshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/snapshot [daily|weekly|monthly] [new]``.

    Without ``new``, the handler first tries to return the latest cached
    snapshot for the requested period.  If ``new`` is appended (or no
    cached snapshot exists), a fresh one is generated.
    """
    args = [a.lower() for a in (context.args or [])]

    # Parse period
    period = SnapshotPeriod.WEEKLY  # default
    for arg in args:
        if arg in _PERIOD_MAP:
            period = _PERIOD_MAP[arg]
            break

    force_new = "new" in args

    await update.message.reply_text(
        f"📊 Generating <b>{period.value}</b> snapshot…",
        parse_mode=ParseMode.HTML,
    )

    try:
        async with sessionmanager.session() as db:
            svc = SnapshotService(db)

            snapshot = None
            if not force_new:
                snapshot = await svc.get_latest_snapshot(period)

            if snapshot is None:
                # Optionally pass AI service for summary generation.
                try:
                    from app.ai.router import ai_router

                    snapshot = await svc.generate_snapshot(period, ai_service=ai_router)
                except ImportError:
                    snapshot = await svc.generate_snapshot(period)

        await update.message.reply_text(
            format_snapshot(snapshot), parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Failed to generate snapshot")
        await update.message.reply_text(
            "❌ Failed to generate snapshot. Please try again later.",
        )
