"""Telegram message formatting helpers.

Every public function returns an **HTML-formatted** string suitable for
``parse_mode=telegram.constants.ParseMode.HTML``.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from app.models.entry import Entry, EntryType, TaskStatus

# ── emoji maps ──────────────────────────────────────────────────────────

ENTRY_TYPE_EMOJI: dict[EntryType, str] = {
    EntryType.NOTE: "📝",
    EntryType.TASK: "✅",
    EntryType.BOOKMARK: "🔖",
    EntryType.CODE: "💻",
    EntryType.VOICE: "🎤",
    EntryType.IDEA: "💡",
    EntryType.LEARNING: "📚",
    EntryType.DECISION: "🎯",
    EntryType.MEMORY: "🧠",
    EntryType.DOCUMENT: "📄",
}

TASK_STATUS_EMOJI: dict[TaskStatus, str] = {
    TaskStatus.TODO: "⬜",
    TaskStatus.IN_PROGRESS: "🔄",
    TaskStatus.DONE: "✅",
}


# ── helpers ─────────────────────────────────────────────────────────────


def _emoji(entry: Entry) -> str:
    """Return the emoji for an entry's type, with a generic fallback."""
    return ENTRY_TYPE_EMOJI.get(entry.entry_type, "📋")


def _truncate(text: str, length: int = 200) -> str:
    """Truncate *text* to *length* characters, appending '…' if trimmed."""
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"


def _safe(text: str) -> str:
    """Escape text for safe embedding inside HTML tags."""
    return html.escape(text)


def _format_tags(tags: list[Any]) -> str:
    """Return a space-separated string of tag labels prefixed with '#'."""
    if not tags:
        return ""
    parts: list[str] = []
    for tag in tags:
        name = tag.name if hasattr(tag, "name") else str(tag)
        parts.append(f"#{_safe(name)}")
    return " ".join(parts)


# ── public API ──────────────────────────────────────────────────────────


def relative_time(dt: datetime) -> str:
    """Convert a *datetime* to a human-friendly relative string.

    The input may be naive (assumed UTC) or aware.  The output is a short
    phrase such as ``"2 min ago"``, ``"1 hour ago"``, ``"yesterday"``, or
    an absolute date for anything older than two days.
    """
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} min ago"
    if seconds < 86400:
        hours = seconds // 3600
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit} ago"
    if seconds < 172800:
        return "yesterday"
    if seconds < 604800:
        days = seconds // 86400
        return f"{days} days ago"
    return dt.strftime("%b %d, %Y")


def format_entry(entry: Entry) -> str:
    """Render a full entry card for display in Telegram (HTML)."""
    emoji = _emoji(entry)
    type_label = entry.entry_type.replace("_", " ").title()
    title = f"<b>{_safe(entry.title)}</b>\n" if entry.title else ""
    content_preview = _safe(_truncate(entry.content)) if entry.content else "<i>No content</i>"

    tags_line = ""
    if hasattr(entry, "tags") and entry.tags:
        tags_line = f"\n🏷 {_format_tags(entry.tags)}"

    ts = relative_time(entry.created_at) if entry.created_at else ""

    return (
        f"{emoji} <b>{_safe(type_label)}</b>  "
        f"<code>#{entry.id}</code>\n"
        f"{title}"
        f"{content_preview}"
        f"{tags_line}\n"
        f"🕐 <i>{ts}</i>"
    )


def format_entry_saved(entry: Entry) -> str:
    """Confirmation message shown right after an entry is persisted."""
    emoji = _emoji(entry)
    type_label = entry.entry_type.replace("_", " ").title()
    preview = _safe(_truncate(entry.content, 120)) if entry.content else ""

    tags_line = ""
    if hasattr(entry, "tags") and entry.tags:
        tags_line = f"\n🏷 {_format_tags(entry.tags)}"

    return (
        f"{emoji} <b>{_safe(type_label)} saved!</b>  "
        f"<code>#{entry.id}</code>\n"
        f"{preview}"
        f"{tags_line}"
    )


def format_search_results(results: list[dict], query: str) -> str:
    """Render search results with rank indicators and headlines."""
    if not results:
        return (
            f"🔍 No results for <b>{_safe(query)}</b>.\n"
            "Try different keywords or broader terms."
        )

    lines: list[str] = [f"🔍 Results for <b>{_safe(query)}</b>:\n"]
    for idx, item in enumerate(results, start=1):
        entry = item.get("entry")
        headline = item.get("headline", "")

        if entry is not None:
            emoji = ENTRY_TYPE_EMOJI.get(entry.entry_type, "📋")
            entry_id = entry.id
            title = entry.title
        else:
            emoji = "📋"
            entry_id = item.get("id", "?")
            title = item.get("title")

        rank = f"<b>{idx}.</b>"
        title_part = f" <b>{_safe(title)}</b>" if title else ""
        headline_part = f"\n   {_safe(headline)}" if headline else ""

        lines.append(
            f"{rank} {emoji}{title_part}  <code>#{entry_id}</code>"
            f"{headline_part}"
        )

    return "\n".join(lines)


def format_task_list(tasks: list[Entry]) -> str:
    """Render a task list with status checkboxes."""
    if not tasks:
        return "📋 No open tasks. You're all caught up! 🎉"

    lines: list[str] = ["📋 <b>Tasks</b>\n"]
    for task in tasks:
        status = task.task_status or TaskStatus.TODO
        emoji = TASK_STATUS_EMOJI.get(status, "⬜")
        content = _safe(_truncate(task.content, 100)) if task.content else "<i>Untitled task</i>"
        lines.append(f"{emoji} <code>#{task.id}</code> {content}")

    return "\n".join(lines)


def format_snapshot(snapshot: Any) -> str:
    """Render a knowledge snapshot summary."""
    period = snapshot.period.value if hasattr(snapshot.period, "value") else str(snapshot.period)
    title = f"📊 <b>{period.title()} Snapshot</b>\n"

    stats_parts: list[str] = []
    if snapshot.entry_count is not None:
        stats_parts.append(f"Entries: <b>{snapshot.entry_count}</b>")
    if snapshot.task_completed_count is not None:
        stats_parts.append(f"Tasks completed: <b>{snapshot.task_completed_count}</b>")
    if snapshot.tag_count is not None:
        stats_parts.append(f"Tags used: <b>{snapshot.tag_count}</b>")
    stats = " · ".join(stats_parts) if stats_parts else ""

    summary = ""
    if snapshot.ai_summary:
        summary = f"\n\n{_safe(snapshot.ai_summary)}"

    ts = ""
    if snapshot.created_at:
        ts = f"\n\n🕐 <i>Generated {relative_time(snapshot.created_at)}</i>"

    return f"{title}{stats}{summary}{ts}"


def format_tag_list(tags: list[dict]) -> str:
    """Render a list of tags with their entry counts."""
    if not tags:
        return "🏷 No tags yet. Start tagging your entries!"

    lines: list[str] = ["🏷 <b>Tags</b>\n"]
    for tag_info in tags:
        name = tag_info.get("name", "unknown")
        count = tag_info.get("count", 0)
        lines.append(f"  #{_safe(name)}  <i>({count})</i>")

    return "\n".join(lines)


def format_help() -> str:
    """Return the full command reference card."""
    return (
        "📖 <b>PKM Bot — Command Reference</b>\n"
        "\n"
        "<b>📝 Capture</b>\n"
        "/note <i>text</i> — Save a quick note\n"
        "/idea <i>text</i> — Capture an idea\n"
        "/task <i>text</i> — Create a to-do item\n"
        "/bookmark <i>url</i> [description] — Save a bookmark\n"
        "/code [lang] <i>code</i> — Save a code snippet\n"
        "\n"
        "<b>🔍 Retrieve</b>\n"
        "/search <i>query</i> — Full-text search\n"
        "/recent [n] — Show recent entries\n"
        "/tags — List all tags with counts\n"
        "\n"
        "<b>✅ Tasks</b>\n"
        "/tasks — List open tasks\n"
        "/done <i>id</i> — Mark a task complete\n"
        "\n"
        "<b>📊 Insights</b>\n"
        "/snapshot [daily|weekly|monthly] — Knowledge snapshot\n"
        "\n"
        "<b>📎 Media</b>\n"
        "Send a 🎤 voice, 📷 photo, or 📄 document\n"
        "— they're saved automatically.\n"
        "\n"
        "<b>💬 Quick capture</b>\n"
        "Just send any text message — it's saved as a note.\n"
    )
