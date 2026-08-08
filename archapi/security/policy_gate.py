from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from archapi.security.secret_scanner import SecretScanner
from archapi.types import GeneratedFile, GenerationResult


@dataclass
class PolicyReport:
    allowed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PolicyGate:
    """
    Output safety gate for generated files (deterministic and LLM paths alike).

    Blocks: absolute/traversal paths, writes to sensitive or protected paths,
    writes to dependency/config files, empty or duplicate files, and generated
    content that looks like it contains a secret.
    """

    BLOCKED_EXACT_FILENAMES = {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
    }

    # Dependency/config files ArchAPI must never create or modify without
    # explicit user authorization — it only generates new API layer code.
    BLOCKED_CONFIG_FILENAMES = {
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "requirements.txt",
        "pyproject.toml",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "setup.py",
        "setup.cfg",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "tsconfig.json",
        ".npmrc",
        "Makefile",
    }

    BLOCKED_PATH_PARTS = {
        ".git",
        ".venv",
        "node_modules",
        ".archapi",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        "vendor",
        "target",
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
        seen_paths = set()

        for generated in files:
            path = Path(generated.path)
            parts = set(path.parts)

            if path.is_absolute():
                errors.append(f"Policy blocked absolute file path: {path}")
            elif ".." in path.parts:
                errors.append(f"Policy blocked path traversal ('..'): {path}")

            if path.name in self.BLOCKED_EXACT_FILENAMES:
                errors.append(f"Policy blocked write to sensitive file: {path}")

            if path.name in self.BLOCKED_CONFIG_FILENAMES:
                errors.append(
                    f"Policy blocked write to dependency/config file without explicit authorization: {path}"
                )

            if parts & self.BLOCKED_PATH_PARTS:
                errors.append(f"Policy blocked write inside protected path: {path}")

            if not generated.content.strip():
                errors.append(f"Policy blocked empty generated file: {path}")

            key = str(path)
            if key in seen_paths:
                errors.append(f"Policy blocked duplicate generated path: {path}")
            seen_paths.add(key)

            lowered = str(path).lower()
            for keyword in self.SENSITIVE_KEYWORDS:
                if keyword in lowered:
                    warnings.append(f"Generated patch touches sensitive area '{keyword}': {path}")

            for pattern_name, pattern in SecretScanner.DEFAULT_PATTERNS.items():
                if pattern.search(generated.content):
                    errors.append(
                        f"Policy blocked generated file containing a possible secret ({pattern_name}): {path}"
                    )

        return PolicyReport(allowed=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_result(self, result: GenerationResult) -> PolicyReport:
        return self.validate_files(result.files)
