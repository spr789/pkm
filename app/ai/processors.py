"""AI content processors for entry analysis and summarization."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIProviderError, ChatMessage
from app.ai.router import AIRouter
from app.models.entry import Entry
from app.services.entry_service import EntryService

logger = logging.getLogger(__name__)


class AIProcessor:
    """Processes entries through AI pipelines for enrichment.

    Provides methods for summarization, tag extraction, and snapshot
    summary generation. Uses the AIRouter for provider-agnostic
    AI access with fallback support.
    """

    def __init__(self, ai_router: AIRouter) -> None:
        self.router = ai_router

    async def process_entry(
        self,
        entry: Entry,
        db: AsyncSession,
        *,
        progress_callback: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        """Run the full AI processing pipeline on an entry.

        Pipeline steps:
        1. Generate summary if content is long enough (>100 chars)
        2. Extract relevant tags from content
        3. Update entry with AI-generated data via EntryService

        This method is designed to run in the background after entry
        creation. It catches all exceptions to avoid crashing the
        background task.

        Args:
            entry: The Entry to process (must have id and content).
            db: AsyncSession for database operations.
            progress_callback: Optional async callable invoked with a
                status label string at each pipeline step so the caller
                can relay live feedback to the user.
        """

        async def _report(label: str) -> None:
            if progress_callback:
                try:
                    await progress_callback(label)
                except Exception:
                    logger.debug("Progress callback failed for: %s", label)

        if not entry.content:
            logger.debug("Skipping AI processing for entry id=%s (no content)", entry.id)
            return

        summary: str | None = None
        extracted_tags: list[str] | None = None

        # Step 1: Generate summary for longer content
        if len(entry.content) > 100:
            await _report("🧠 Generating summary…")
            try:
                summary = await self.summarize(entry.content)
                logger.info("Generated summary for entry id=%s", entry.id)
            except AIProviderError:
                logger.exception("Failed to generate summary for entry id=%s", entry.id)

        # Step 2: Extract tags
        await _report("🏷 Extracting tags…")
        try:
            existing_tag_names = [tag.name for tag in entry.tags] if entry.tags else []
            extracted_tags = await self.extract_tags(entry.content, existing_tags=existing_tag_names)
            logger.info("Extracted tags for entry id=%s: %s", entry.id, extracted_tags)
        except AIProviderError:
            logger.exception("Failed to extract tags for entry id=%s", entry.id)

        # Step 3: Update entry with AI metadata
        if summary is not None or extracted_tags:
            await _report("💾 Saving enrichment…")
            try:
                service = EntryService(db)
                await service.update_ai_metadata(
                    entry_id=entry.id,
                    summary=summary,
                    tags=extracted_tags,
                )
                await db.commit()
                logger.info("Updated AI metadata for entry id=%s", entry.id)
            except Exception:
                await db.rollback()
                logger.exception("Failed to update AI metadata for entry id=%s", entry.id)

    async def summarize(self, text: str) -> str:
        """Generate a concise summary of the given text.

        Args:
            text: The text content to summarize.

        Returns:
            A 1-2 sentence summary string.
        """
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are a precise summarization assistant for a personal knowledge "
                    "management system. Your job is to create concise, informative summaries.\n\n"
                    "Rules:\n"
                    "- Write exactly 1-2 sentences\n"
                    "- Capture the core idea or action item\n"
                    "- Use clear, direct language\n"
                    "- Do NOT include phrases like 'This entry is about' or 'The user'\n"
                    "- Do NOT use markdown formatting\n"
                    "- Return ONLY the summary text, nothing else"
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Summarize the following:\n\n{text[:3000]}",
            ),
        ]

        response = await self.router.chat_with_fallback(
            messages, temperature=0.3, max_tokens=200
        )
        return response.content.strip()

    async def extract_tags(
        self,
        text: str,
        existing_tags: list[str] | None = None,
    ) -> list[str]:
        """Extract relevant tags from text content.

        Args:
            text: The text content to analyze.
            existing_tags: Optional list of existing tags in the system
                to encourage reuse and consistency.

        Returns:
            List of 2-5 lowercase tag strings.
        """
        existing_context = ""
        if existing_tags:
            tags_sample = existing_tags[:50]
            existing_context = (
                f"\n\nExisting tags in the system (prefer reusing these when relevant): "
                f"{', '.join(tags_sample)}"
            )

        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are a tag extraction assistant for a personal knowledge management system. "
                    "Your job is to identify the most relevant tags for organizing content.\n\n"
                    "Rules:\n"
                    "- Extract 2 to 5 tags maximum\n"
                    "- Tags must be lowercase, single words or hyphenated (e.g., 'machine-learning')\n"
                    "- Tags should be specific but not overly narrow\n"
                    "- Prefer reusing existing tags from the system when they fit\n"
                    "- Focus on topics, technologies, concepts, and categories\n"
                    "- Do NOT include generic tags like 'note', 'entry', 'text', 'content'\n"
                    "- Return ONLY a comma-separated list of tags, nothing else\n"
                    "- Example output: python, web-scraping, automation"
                    f"{existing_context}"
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Extract tags from the following content:\n\n{text[:3000]}",
            ),
        ]

        response = await self.router.chat_with_fallback(
            messages, temperature=0.2, max_tokens=100
        )

        # Parse comma-separated tags
        raw_tags = response.content.strip()
        tags = [
            tag.strip().lower().replace(" ", "-")
            for tag in raw_tags.split(",")
            if tag.strip()
        ]

        # Filter out empty or too-long tags, limit to 5
        tags = [t for t in tags if 1 <= len(t) <= 50][:5]

        return tags

    async def generate_snapshot_summary(
        self,
        entries_text: str,
        period: str,
    ) -> str:
        """Generate a structured summary for a periodic snapshot.

        Args:
            entries_text: Formatted text of entries in the period.
            period: The period type ('daily', 'weekly', 'monthly').

        Returns:
            Markdown-formatted summary with structured sections.
        """
        period_label = period.capitalize()

        messages = [
            ChatMessage(
                role="system",
                content=(
                    f"You are a personal knowledge analyst. Generate a {period_label} knowledge "
                    f"snapshot summary from the entries provided.\n\n"
                    "Format the summary in markdown with these sections (skip empty sections):\n\n"
                    "## 📚 Learned\n"
                    "Key learnings and insights from this period.\n\n"
                    "## 🔨 Built\n"
                    "Things created, built, or implemented.\n\n"
                    "## 🔧 Solved\n"
                    "Problems solved or challenges overcome.\n\n"
                    "## 💡 Ideas\n"
                    "New ideas, plans, or inspiration.\n\n"
                    "## 📝 Key Notes\n"
                    "Important notes and observations.\n\n"
                    "Rules:\n"
                    "- Be concise: 2-3 bullet points per section maximum\n"
                    "- Use clear, actionable language\n"
                    "- Skip sections that have no relevant entries\n"
                    "- Start each bullet with a brief, bold topic label\n"
                    "- Return ONLY the markdown summary, no preamble"
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Generate a {period_label} snapshot summary from these entries:\n\n{entries_text[:6000]}",
            ),
        ]

        response = await self.router.chat_with_fallback(
            messages, temperature=0.5, max_tokens=1500
        )
        return response.content.strip()
