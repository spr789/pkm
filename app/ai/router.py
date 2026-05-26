"""AI router for provider management and request routing."""

from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.base import (
    AIProvider,
    AIProviderError,
    AIRateLimitError,
    ChatMessage,
    ChatResponse,
)
from app.ai.override import get_model, get_provider
from app.config import settings

logger = logging.getLogger(__name__)

# Provider fallback order
FALLBACK_CHAIN = ["opencode", "openrouter", "openai", "anthropic", "gemini", "sarvam"]


class AIRouter:
    """Routes AI requests to configured providers with fallback support.

    Lazily creates provider instances based on available API keys.
    Provides retry logic with exponential backoff and automatic
    fallback across providers when the primary fails.
    """

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    def _get_api_key(self, provider_name: str) -> str | None:
        """Get the API key for a provider from settings.

        Args:
            provider_name: Provider identifier.

        Returns:
            The API key string or None if not configured.
        """
        key_map = {
            "opencode": "opencode_api_key",
            "openrouter": "openrouter_api_key",
            "openai": "openai_api_key",
            "anthropic": "anthropic_api_key",
            "gemini": "google_api_key",
            "sarvam": "sarvam_api_key",
        }

        attr = key_map.get(provider_name)
        if attr is None:
            return None

        secret = getattr(settings, attr, None)
        if secret is None:
            return None

        # Handle SecretStr
        key_value = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
        return key_value if key_value else None

    def _create_provider(self, name: str) -> AIProvider | None:
        """Create a provider instance by name.

        Args:
            name: Provider identifier ('openrouter', 'openai', 'anthropic', 'gemini').

        Returns:
            An AIProvider instance or None if the API key is missing.
        """
        api_key = self._get_api_key(name)
        if not api_key:
            return None

        if name == "opencode":
            from app.ai.providers.opencode_provider import OpenCodeProvider

            return OpenCodeProvider(api_key)

        if name == "openrouter":
            from app.ai.providers.openrouter import OpenRouterProvider

            return OpenRouterProvider(api_key)

        if name == "openai":
            from app.ai.providers.openai_provider import OpenAIProvider

            return OpenAIProvider(api_key)

        if name == "anthropic":
            from app.ai.providers.anthropic_provider import AnthropicProvider

            return AnthropicProvider(api_key)

        if name == "gemini":
            from app.ai.providers.google_provider import GeminiProvider

            return GeminiProvider(api_key)

        if name == "sarvam":
            from app.ai.providers.sarvam_provider import SarvamProvider

            return SarvamProvider(api_key)

        logger.warning("Unknown provider name: %s", name)
        return None

    def get_provider(self, name: str) -> AIProvider:
        """Get or create a specific provider by name.

        Args:
            name: Provider identifier.

        Returns:
            The AIProvider instance.

        Raises:
            AIProviderError: If the provider is not available (missing API key).
        """
        if name not in self._providers:
            provider = self._create_provider(name)
            if provider is None:
                raise AIProviderError(
                    f"Provider '{name}' is not available (API key not configured)",
                    provider=name,
                )
            self._providers[name] = provider

        return self._providers[name]

    def get_default_provider(self) -> AIProvider:
        """Get the default provider from settings or override."""
        default_name = get_provider() or getattr(settings, "ai_default_provider", "openrouter")
        return self.get_provider(default_name)

    def _get_default_model(self) -> str | None:
        """Get the model override if set, otherwise None."""
        return get_model()

    def _get_available_providers(self) -> list[str]:
        """Get list of provider names that have API keys configured.

        Returns:
            List of available provider name strings.
        """
        available = []
        for name in FALLBACK_CHAIN:
            if self._get_api_key(name):
                available.append(name)
        return available

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(AIRateLimitError),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[ChatMessage],
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        if provider is not None:
            ai_provider = self.get_provider(provider)
        else:
            ai_provider = self.get_default_provider()

        model = model or get_model() or None
        return await ai_provider.chat(messages, model=model, **kwargs)

    async def chat_with_fallback(
        self,
        messages: list[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        available = self._get_available_providers()
        if not available:
            raise AIProviderError(
                "No AI providers available — no API keys configured",
                provider="none",
            )

        default_name = get_provider() or getattr(settings, "ai_default_provider", "openrouter")
        if default_name in available:
            available = [default_name] + [p for p in available if p != default_name]

        last_error: AIProviderError | None = None
        for provider_name in available:
            try:
                logger.debug("Trying provider: %s", provider_name)
                return await self.chat(messages, provider=provider_name, **kwargs)
            except AIProviderError as exc:
                logger.warning(
                    "Provider %s failed: %s — trying next",
                    provider_name,
                    exc,
                )
                last_error = exc
                continue

        raise AIProviderError(
            f"All AI providers failed. Last error: {last_error}",
            provider="fallback",
        )

    async def close(self) -> None:
        """Close all active provider HTTP clients."""
        for name, provider in self._providers.items():
            try:
                await provider.close()
                logger.debug("Closed provider: %s", name)
            except Exception:
                logger.exception("Error closing provider: %s", name)
        self._providers.clear()


# Module-level singleton
ai_router = AIRouter()
