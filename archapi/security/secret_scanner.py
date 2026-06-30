from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class SecretFinding:
    file: str
    line: int
    pattern: str
    preview: str


@dataclass
class SecretScanReport:
    success: bool
    findings: List[SecretFinding] = field(default_factory=list)


class SecretScanner:
    """
    Lightweight local secret scanner.

    This is not a replacement for Gitleaks or TruffleHog.
    It is a first safety layer for ArchAPI v0.1.
    """

    DEFAULT_PATTERNS = {
        "api_key_assignment": re.compile(r"(?i)(api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
        "secret_assignment": re.compile(r"(?i)(secret|client_secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
        "token_assignment": re.compile(r"(?i)(token|access_token|refresh_token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}"),
        "private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    }

    IGNORED_DIRS = {
        ".git",
        ".venv",
        "node_modules",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        "vendor",
        "target",
        ".archapi",
    }

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)

    def scan(self) -> SecretScanReport:
        findings: List[SecretFinding] = []

        for path in self.project_path.rglob("*"):
            if path.is_dir():
                continue

            if any(part in self.IGNORED_DIRS for part in path.parts):
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = str(path.relative_to(self.project_path))

            for line_no, line in enumerate(text.splitlines(), start=1):
                for pattern_name, pattern in self.DEFAULT_PATTERNS.items():
                    if pattern.search(line):
                        findings.append(
                            SecretFinding(
                                file=rel,
                                line=line_no,
                                pattern=pattern_name,
                                preview=self._preview(line),
                            )
                        )

        return SecretScanReport(success=len(findings) == 0, findings=findings)

    def _preview(self, line: str) -> str:
        clean = line.strip()
        if len(clean) <= 80:
            return clean
        return clean[:77] + "..."
