"""Abstract base class and data structures for AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str  # 'system', 'user', 'assistant'
    content: str


@dataclass
class ChatResponse:
    """Response from an AI provider chat completion."""

    content: str
    model: str
    provider: str
    usage: dict | None = field(default=None)
    reasoning: str | None = field(default=None)


class AIProvider(ABC):
    """Abstract base class for all AI providers.

    Each provider must implement the chat method for sending messages
    and the close method for cleaning up resources (e.g., HTTP clients).
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a chat completion request to the AI provider.

        Args:
            messages: List of chat messages forming the conversation.
            model: Optional model override; provider uses its default if None.
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Maximum tokens in the response.

        Returns:
            ChatResponse with the generated content and metadata.

        Raises:
            AIProviderError: If the API request fails.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        ...


class AIProviderError(Exception):
    """Raised when an AI provider encounters an error."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


class AIRateLimitError(AIProviderError):
    """Raised when the AI provider returns a rate limit error (429)."""

    pass
