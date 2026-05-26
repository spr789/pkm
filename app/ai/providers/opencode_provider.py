from __future__ import annotations

import logging

import httpx

from app.ai.base import AIProvider, AIProviderError, AIRateLimitError, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-v4-flash-free"
BASE_URL = "https://opencode.ai/zen/v1"


class OpenCodeProvider(AIProvider):
    """AI provider using the OpenCode Zen API (OpenAI-compatible)."""

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        self.default_model = default_model
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=headers,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
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
                f"OpenCode request timed out: {exc}", provider="opencode",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"OpenCode HTTP error: {exc}", provider="opencode",
            ) from exc

        if response.status_code == 429:
            raise AIRateLimitError(
                "OpenCode rate limit exceeded",
                provider="opencode",
                status_code=429,
                response_body=response.text,
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"OpenCode API error {response.status_code}: {response.text}",
                provider="opencode",
                status_code=response.status_code,
                response_body=response.text,
            )

        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(
                f"Unexpected OpenCode response format: {data}",
                provider="opencode",
            ) from exc

        usage = data.get("usage")

        logger.debug("OpenCode response model=%s tokens=%s", model, usage)
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider="opencode",
            usage=usage,
        )

    async def close(self) -> None:
        await self._client.aclose()
