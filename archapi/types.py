from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DetectionResult:
    framework: str
    confidence: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class ScanResult:
    framework: str
    project_path: Path
    routes: List[Path] = field(default_factory=list)
    controllers: List[Path] = field(default_factory=list)
    services: List[Path] = field(default_factory=list)
    models: List[Path] = field(default_factory=list)
    schemas: List[Path] = field(default_factory=list)
    middleware: List[Path] = field(default_factory=list)
    tests: List[Path] = field(default_factory=list)
    config_files: List[Path] = field(default_factory=list)
    unknown: List[Path] = field(default_factory=list)


@dataclass
class APIGenome:
    framework: str
    route_style: str = "unknown"
    controller_style: str = "unknown"
    service_style: str = "unknown"
    model_style: str = "unknown"
    schema_style: str = "unknown"
    auth_style: str = "unknown"
    error_style: str = "unknown"
    test_style: str = "unknown"
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class APIPlan:
    request: str
    method: str
    path: str
    entities: List[str]
    layers: List[str]
    generation_allowed: bool
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedFile:
    path: Path
    content: str
    action: str = "create"


@dataclass
class ValidationReport:
    success: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    project_path: Path
    plan: APIPlan
    files: List[GeneratedFile]
    validation_report: ValidationReport
    warnings: List[str] = field(default_factory=list)

    @property
    def diff(self) -> str:
        chunks: List[str] = []
        for file in self.files:
            chunks.append(f"--- {file.path}")
            chunks.append(f"+++ {file.path}")
            chunks.append(file.content)
            chunks.append("")
        return "\n".join(chunks)

    def apply(self) -> None:
        if not self.validation_report.success:
            raise RuntimeError(
                "Cannot apply generated files because validation failed: "
                + "; ".join(self.validation_report.errors)
            )

        for generated in self.files:
            target = self.project_path / generated.path
            target.parent.mkdir(parents=True, exist_ok=True)

            if target.exists() and generated.action == "create":
                raise FileExistsError(f"Refusing to overwrite existing file: {target}")

            target.write_text(generated.content, encoding="utf-8")
