from __future__ import annotations

import os
from typing import Optional

from archapi.llm.base import LLMProvider
from archapi.llm.errors import LLMProviderError


_DEFAULT_MODEL = "gpt-4o-mini"
_SYSTEM_PROMPT = (
    "You are ArchAPI, an expert API engineer. "
    "Generate architecture-matching REST API code in valid JSON only. "
    "Do not include any text outside the JSON object."
)


class OpenAIProvider(LLMProvider):
    """
    LLM provider backed by the OpenAI Chat Completions API.

    Requires the ``openai`` package (``pip install archapi[openai]``).

    API key resolution order:
    1. ``api_key`` constructor argument
    2. ``OPENAI_API_KEY`` environment variable

    Example::

        provider = OpenAIProvider(model="gpt-4o-mini")
        response = provider.complete(prompt)
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

        if not self._api_key:
            raise LLMProviderError(
                "OpenAI API key not found. "
                "Set the OPENAI_API_KEY environment variable or pass api_key= to OpenAIProvider."
            )

        self._client = self._build_client()

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, prompt: str) -> str:
        """
        Send *prompt* to OpenAI and return the raw text response.

        :raises LLMProviderError: On API errors, network failures, or empty responses.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:
            raise LLMProviderError(f"OpenAI API request failed: {exc}") from exc

        try:
            text = response.choices[0].message.content or ""
        except (IndexError, AttributeError) as exc:
            raise LLMProviderError(f"Unexpected OpenAI response structure: {exc}") from exc

        if not text.strip():
            raise LLMProviderError("OpenAI returned an empty response.")

        return text

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_client(self):
        try:
            import openai  # noqa: PLC0415 — lazy import so optional dep works
        except ImportError as exc:
            raise LLMProviderError(
                "The 'openai' package is required for OpenAIProvider. "
                "Install it with: pip install archapi[openai]"
            ) from exc

        return openai.OpenAI(api_key=self._api_key)
