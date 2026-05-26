"""OpenRouter AI provider implementation."""

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

DEFAULT_MODEL = "deepseek/deepseek-chat-v3-0324:free"
BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(AIProvider):
    """AI provider using the OpenRouter API.

    OpenRouter provides access to multiple AI models through an
    OpenAI-compatible API interface. This is the primary/default
    provider for the PKM system.
    """

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/pkm-system",
                "X-Title": "PKM Personal Knowledge Manager",
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
        """Send a chat completion request to OpenRouter.

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

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                f"OpenRouter request timed out: {exc}",
                provider="openrouter",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"OpenRouter HTTP error: {exc}",
                provider="openrouter",
            ) from exc

        if response.status_code == 429:
            raise AIRateLimitError(
                "OpenRouter rate limit exceeded",
                provider="openrouter",
                status_code=429,
                response_body=response.text,
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"OpenRouter API error {response.status_code}: {response.text}",
                provider="openrouter",
                status_code=response.status_code,
                response_body=response.text,
            )

        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(
                f"Unexpected OpenRouter response format: {data}",
                provider="openrouter",
            ) from exc

        usage = data.get("usage")

        logger.debug("OpenRouter response model=%s tokens=%s", model, usage)
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider="openrouter",
            usage=usage,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
