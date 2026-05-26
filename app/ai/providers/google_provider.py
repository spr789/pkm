"""Google Gemini API provider implementation."""

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

DEFAULT_MODEL = "gemini-2.0-flash"
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
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

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

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
