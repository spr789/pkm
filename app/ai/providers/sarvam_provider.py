from __future__ import annotations

import logging

import httpx

from app.ai.base import AIProvider, AIProviderError, AIRateLimitError, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sarvam-30b"
BASE_URL = "https://api.sarvam.ai/v1"


class SarvamProvider(AIProvider):
    """AI provider using the Sarvam AI API (OpenAI-compatible)."""

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
        model = model or self.default_model

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": "low",
        }

        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                f"Sarvam request timed out: {exc}", provider="sarvam",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"Sarvam HTTP error: {exc}", provider="sarvam",
            ) from exc

        if response.status_code == 429:
            raise AIRateLimitError(
                "Sarvam rate limit exceeded",
                provider="sarvam",
                status_code=429,
                response_body=response.text,
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"Sarvam API error {response.status_code}: {response.text}",
                provider="sarvam",
                status_code=response.status_code,
                response_body=response.text,
            )

        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise AIProviderError(
                f"Unexpected Sarvam response format: {data}",
                provider="sarvam",
            ) from exc

        usage = data.get("usage")
        reasoning = data.get("choices", [{}])[0].get("message", {}).get("reasoning_content")

        logger.debug("Sarvam response model=%s tokens=%s", model, usage)
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider="sarvam",
            usage=usage,
            reasoning=reasoning,
        )

    async def close(self) -> None:
        await self._client.aclose()
