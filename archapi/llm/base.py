from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    """Interface for real-time LLM providers."""

    def generate(self, prompt: str) -> str:
        """Return raw model text for the given prompt."""
        raise NotImplementedError
