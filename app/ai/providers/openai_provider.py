"""OpenAI API provider implementation."""

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

DEFAULT_MODEL = "gpt-4o-mini"
BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(AIProvider):
    """AI provider using the OpenAI API.

    Standard OpenAI chat completions API with support for all
    GPT-family models.
    """

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
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
        """Send a chat completion request to OpenAI.

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
                f"OpenAI request timed out: {exc}",
                provider="openai",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"OpenAI HTTP error: {exc}",
                provider="openai",
            ) from exc

        if response.status_code == 429:
            raise AIRateLimitError(
                "OpenAI rate limit exceeded",
                provider="openai",
                status_code=429,
                response_body=response.text,
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"OpenAI API error {response.status_code}: {response.text}",
                provider="openai",
                status_code=response.status_code,
                response_body=response.text,
            )

        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(
                f"Unexpected OpenAI response format: {data}",
                provider="openai",
            ) from exc

        usage = data.get("usage")

        logger.debug("OpenAI response model=%s tokens=%s", model, usage)
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider="openai",
            usage=usage,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
