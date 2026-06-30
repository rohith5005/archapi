from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class OpenAIProvider:
    """
    Real-time OpenAI provider using the Responses API.

    Required environment variable:
        OPENAI_API_KEY

    Optional environment variables:
        ARCHAPI_LLM_MODEL       default: gpt-5-mini
        OPENAI_BASE_URL         default: https://api.openai.com/v1
        ARCHAPI_LLM_MAX_TOKENS  default: 6000
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 90,
        max_output_tokens: Optional[int] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("ARCHAPI_LLM_MODEL", "gpt-5-mini")
        self.base_url = (
            base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.timeout = timeout
        self.max_output_tokens = int(
            max_output_tokens or os.getenv("ARCHAPI_LLM_MAX_TOKENS", "6000")
        )

        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for OpenAIProvider. "
                "Set OPENAI_API_KEY before using ArchAPI with use_llm=True."
            )

    def complete(self, prompt: str) -> str:
        """Compatibility method used by ArchAPI core."""
        return self.generate(prompt)

    def generate(self, prompt: str) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "instructions": (
                "You are ArchAPI's architecture-aware code generation engine. "
                "Return only valid JSON. Do not wrap output in markdown fences."
            ),
            "input": prompt,
            "max_output_tokens": self.max_output_tokens,
        }

        request = urllib.request.Request(
            url=f"{self.base_url}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
                context=self._ssl_context(),
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OpenAI request failed with HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI request failed: {exc}") from exc

        data = json.loads(raw)
        return self._extract_text(data)

    def _ssl_context(self):
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()

    def _extract_text(self, response: Dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        chunks: List[str] = []

        for item in response.get("output", []):
            if not isinstance(item, dict):
                continue

            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue

                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    chunks.append(content["text"])

        text = "\n".join(chunks).strip()

        if not text:
            raise RuntimeError(f"OpenAI response did not include output text: {response}")

        return text
