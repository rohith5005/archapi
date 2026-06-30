from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Concrete implementations (OpenAI, Anthropic, Gemini, local models) must
    implement `complete()`, which accepts a prompt string and returns the raw
    model response as a string.
    """

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """
        Send ``prompt`` to the underlying LLM and return the raw text response.

        :param prompt: The full prompt to send.
        :returns: Raw response text from the model.
        :raises LLMProviderError: If the request fails for any reason.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier (e.g. ``"gpt-4o-mini"``)."""
        raise NotImplementedError
