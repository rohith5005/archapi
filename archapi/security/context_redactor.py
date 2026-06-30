from __future__ import annotations

import re


class ContextRedactor:
    """
    Redacts obvious sensitive values before text is sent to an language model.
    """

    REDACTIONS = [
        (
            re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)['\"]?[A-Za-z0-9_\-]{8,}['\"]?"),
            r"\1[REDACTED_API_KEY]",
        ),
        (
            re.compile(r"(?i)((access_token|refresh_token|token)\s*[:=]\s*)['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?"),
            r"\1[REDACTED_TOKEN]",
        ),
        (
            re.compile(r"(?i)((secret|client_secret)\s*[:=]\s*)['\"]?[A-Za-z0-9_\-]{8,}['\"]?"),
            r"\1[REDACTED_SECRET]",
        ),
        (
            re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?-----END (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.DOTALL),
            "[REDACTED_PRIVATE_KEY]",
        ),
        (
            re.compile(r"AKIA[0-9A-Z]{16}"),
            "[REDACTED_AWS_ACCESS_KEY]",
        ),
    ]

    def redact(self, text: str) -> str:
        redacted = text
        for pattern, replacement in self.REDACTIONS:
            redacted = pattern.sub(replacement, redacted)
        return redacted
