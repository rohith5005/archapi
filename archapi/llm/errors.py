from __future__ import annotations


class LLMProviderError(Exception):
    """Raised when the LLM provider fails to complete a request."""


class LLMParseError(Exception):
    """Raised when the LLM response cannot be parsed into the expected structure."""
