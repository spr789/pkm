"""Google Gemini API provider implementation."""

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

DEFAULT_MODEL = "gemini-2.5-flash"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(AIProvider):
    """AI provider using the Google Gemini API.

    Converts OpenAI-style messages to Gemini's contents array format
    with role/parts structure. The API key is passed as a query
    parameter rather than a header.
    """

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    def _build_payload(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[dict, str]:
        """Build the Gemini request payload and return (payload, model)."""
        # Convert messages to Gemini format
        system_parts: list[str] = []
        contents: list[dict] = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            else:
                # Gemini uses 'user' and 'model' roles
                gemini_role = "model" if msg.role == "assistant" else "user"
                contents.append(
                    {
                        "role": gemini_role,
                        "parts": [{"text": msg.content}],
                    }
                )

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_parts:
            payload["system_instruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }

        return payload, model

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a generateContent request to the Gemini API.

        Converts ChatMessage list to Gemini's format:
        - System messages go into system_instruction
        - User/assistant messages go into contents array with role/parts

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
        payload, model = self._build_payload(messages, model, temperature, max_tokens)

        url = f"/models/{model}:generateContent"
        params = {"key": self.api_key}

        try:
            response = await self._client.post(url, json=payload, params=params)
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                f"Gemini request timed out: {exc}",
                provider="gemini",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"Gemini HTTP error: {exc}",
                provider="gemini",
            ) from exc

        if response.status_code == 429:
            raise AIRateLimitError(
                "Gemini rate limit exceeded",
                provider="gemini",
                status_code=429,
                response_body=response.text,
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"Gemini API error {response.status_code}: {response.text}",
                provider="gemini",
                status_code=response.status_code,
                response_body=response.text,
            )

        data = response.json()

        try:
            candidates = data["candidates"]
            content_parts = candidates[0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in content_parts)
        except (KeyError, IndexError) as exc:
            raise AIProviderError(
                f"Unexpected Gemini response format: {data}",
                provider="gemini",
            ) from exc

        # Gemini usage metadata
        usage_metadata = data.get("usageMetadata")
        usage_dict = None
        if usage_metadata:
            usage_dict = {
                "prompt_tokens": usage_metadata.get("promptTokenCount"),
                "completion_tokens": usage_metadata.get("candidatesTokenCount"),
                "total_tokens": usage_metadata.get("totalTokenCount"),
            }

        logger.debug("Gemini response model=%s usage=%s", model, usage_dict)
        return ChatResponse(
            content=content,
            model=model,
            provider="gemini",
            usage=usage_dict,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a generateContent request using Gemini's streaming endpoint.

        Uses ``streamGenerateContent`` with ``alt=sse`` to receive
        server-sent events.  Each event contains a JSON chunk with
        partial candidates.  Reasoning/thinking tokens arrive in parts
        with ``thought: true``; regular content arrives in normal parts.
        """
        model = model or self.default_model
        payload, model = self._build_payload(messages, model, temperature, max_tokens)

        url = f"/models/{model}:streamGenerateContent"
        params = {"key": self.api_key, "alt": "sse"}

        try:
            async with self._client.stream(
                "POST", url, json=payload, params=params
            ) as response:
                if response.status_code == 429:
                    raise AIRateLimitError(
                        "Gemini rate limit exceeded",
                        provider="gemini",
                        status_code=429,
                    )
                if response.status_code != 200:
                    body = await response.aread()
                    raise AIProviderError(
                        f"Gemini stream error {response.status_code}: {body.decode()}",
                        provider="gemini",
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

                    # Extract parts from the first candidate
                    candidates = data.get("candidates", [])
                    if not candidates:
                        continue

                    parts = (
                        candidates[0]
                        .get("content", {})
                        .get("parts", [])
                    )

                    content_delta = ""
                    reasoning_delta = ""

                    for part in parts:
                        text = part.get("text", "")
                        if part.get("thought", False):
                            reasoning_delta += text
                        else:
                            content_delta += text

                    if content_delta or reasoning_delta:
                        yield StreamChunk(
                            content=content_delta,
                            reasoning=reasoning_delta,
                            model=model,
                            provider="gemini",
                        )

        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise AIProviderError(
                f"Gemini stream error: {exc}",
                provider="gemini",
            ) from exc

        # Final done chunk
        yield StreamChunk(model=model, provider="gemini", done=True)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

