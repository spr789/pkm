"""Abstract base class and data structures for AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
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


@dataclass
class StreamChunk:
    """A single chunk from a streaming AI response.

    Attributes:
        content: New content text delta (may be empty).
        reasoning: New reasoning/thinking text delta (may be empty).
        model: Model identifier (set on first or last chunk).
        provider: Provider identifier.
        done: True when this is the final chunk.
    """

    content: str = ""
    reasoning: str = ""
    model: str = ""
    provider: str = ""
    done: bool = False


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

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion, yielding chunks as they arrive.

        The default implementation falls back to the non-streaming
        ``chat()`` method and yields a single done-chunk.  Providers
        that support native streaming should override this.
        """
        response = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens,
        )
        yield StreamChunk(
            content=response.content,
            reasoning=response.reasoning or "",
            model=response.model,
            provider=response.provider,
            done=True,
        )

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

