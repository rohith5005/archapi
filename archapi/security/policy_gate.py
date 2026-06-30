from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from archapi.types import GeneratedFile, GenerationResult


@dataclass
class PolicyReport:
    allowed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PolicyGate:
    """
    Simple policy gate for v0.1.

    Blocks generated patches from touching risky files and sensitive paths.
    """

    BLOCKED_EXACT_FILENAMES = {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
    }

    BLOCKED_PATH_PARTS = {
        ".git",
        ".venv",
        "node_modules",
        ".archapi",
    }

    SENSITIVE_KEYWORDS = {
        "payment",
        "billing",
        "auth.core",
        "passport",
        "oauth",
        "jwt.secret",
    }

    def validate_files(self, files: List[GeneratedFile]) -> PolicyReport:
        errors: List[str] = []
        warnings: List[str] = []

        for generated in files:
            path = Path(generated.path)
            parts = set(path.parts)

            if path.name in self.BLOCKED_EXACT_FILENAMES:
                errors.append(f"Policy blocked write to sensitive file: {path}")

            if parts & self.BLOCKED_PATH_PARTS:
                errors.append(f"Policy blocked write inside protected path: {path}")

            lowered = str(path).lower()
            for keyword in self.SENSITIVE_KEYWORDS:
                if keyword in lowered:
                    warnings.append(f"Generated patch touches sensitive area '{keyword}': {path}")

        return PolicyReport(allowed=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_result(self, result: GenerationResult) -> PolicyReport:
        return self.validate_files(result.files)
