"""OpenRouter AI provider implementation."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.ai.base import (
    AIProvider,
    AIProviderError,
    AIRateLimitError,
    ChatMessage,
    ChatResponse,
    StreamChunk,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "google/gemini-2.5-pro"
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

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion request to OpenRouter."""
        model = model or self.default_model

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload
            ) as response:
                if response.status_code == 429:
                    raise AIRateLimitError(
                        "OpenRouter rate limit exceeded",
                        provider="openrouter",
                        status_code=429,
                    )
                if response.status_code != 200:
                    body = await response.aread()
                    raise AIProviderError(
                        f"OpenRouter stream error {response.status_code}: {body.decode()}",
                        provider="openrouter",
                        status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    json_str = line[len("data: "):]
                    if not json_str or json_str == "[DONE]":
                        continue

                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    content_delta = delta.get("content", "") or ""
                    reasoning_delta = (
                        delta.get("reasoning_content", "")
                        or delta.get("reasoning", "")
                        or ""
                    )

                    if content_delta or reasoning_delta:
                        yield StreamChunk(
                            content=content_delta,
                            reasoning=reasoning_delta,
                            model=model,
                            provider="openrouter",
                        )

        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise AIProviderError(
                f"OpenRouter stream error: {exc}",
                provider="openrouter",
            ) from exc

        # Final done chunk
        yield StreamChunk(model=model, provider="openrouter", done=True)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

