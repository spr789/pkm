"""Anthropic API provider implementation."""

from __future__ import annotations

import logging

import httpx

from app.ai.base import (
    AIProvider,
    AIProviderError,
    AIRateLimitError,
    ChatMessage,
    ChatResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"
BASE_URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"


class AnthropicProvider(AIProvider):
    """AI provider using the Anthropic Messages API.

    Handles Anthropic's unique API format where the system message
    is passed as a separate top-level parameter rather than in the
    messages array.
    """

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "anthropic-version": API_VERSION,
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a message creation request to the Anthropic API.

        System messages are extracted and passed as the top-level
        'system' parameter per Anthropic API requirements.

        Args:
            messages: List of chat messages.
            model: Model identifier; uses default if None.
            temperature: Sampling temperature.
            max_tokens: Maximum response tokens.

        Returns:
            ChatResponse with generated content.

        Raises:
            AIRateLimitError: On 429 rate limit responses.
            AIProviderError: On other API errors.
        """
        model = model or self.default_model

        # Separate system messages from conversation messages
        system_parts: list[str] = []
        conversation_messages: list[dict] = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            else:
                conversation_messages.append(
                    {"role": msg.role, "content": msg.content}
                )

        payload: dict = {
            "model": model,
            "messages": conversation_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        try:
            response = await self._client.post("/messages", json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                f"Anthropic request timed out: {exc}",
                provider="anthropic",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"Anthropic HTTP error: {exc}",
                provider="anthropic",
            ) from exc

        if response.status_code == 429:
            raise AIRateLimitError(
                "Anthropic rate limit exceeded",
                provider="anthropic",
                status_code=429,
                response_body=response.text,
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"Anthropic API error {response.status_code}: {response.text}",
                provider="anthropic",
                status_code=response.status_code,
                response_body=response.text,
            )

        data = response.json()

        try:
            # Anthropic returns content as a list of content blocks
            content_blocks = data["content"]
            content = "".join(
                block["text"] for block in content_blocks if block["type"] == "text"
            )
        except (KeyError, IndexError) as exc:
            raise AIProviderError(
                f"Unexpected Anthropic response format: {data}",
                provider="anthropic",
            ) from exc

        usage = data.get("usage")
        usage_dict = None
        if usage:
            usage_dict = {
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
                "total_tokens": (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)),
            }

        logger.debug("Anthropic response model=%s usage=%s", model, usage_dict)
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider="anthropic",
            usage=usage_dict,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
