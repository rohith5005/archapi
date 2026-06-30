from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from archapi.frameworks.base import FrameworkAdapter
from archapi.planning.intent_planner import IntentPlanner
from archapi.types import (
    APIPlan,
    APIGenome,
    DetectionResult,
    GeneratedFile,
    ScanResult,
    ValidationReport,
)


IGNORED_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "coverage",
    ".venv",
    "__pycache__",
    "vendor",
    "target",
    ".archapi",
    "sample_projects",
    "archapi.egg-info",
}


class GenericAdapter(FrameworkAdapter):
    name = "generic"

    def detect(self, project_path: Path) -> DetectionResult:
        return DetectionResult("generic", 0.10, ["Fallback generic adapter"])

    def scan(self, project_path: Path) -> ScanResult:
        result = ScanResult(framework=self.name, project_path=project_path)

        for path in self._walk_files(project_path):
            lower = str(path).lower()

            if "route" in lower or "url" in lower:
                result.routes.append(path)
            elif "controller" in lower or "handler" in lower or "view" in lower:
                result.controllers.append(path)
            elif "service" in lower:
                result.services.append(path)
            elif "model" in lower or "entity" in lower:
                result.models.append(path)
            elif "schema" in lower or "serializer" in lower or "dto" in lower:
                result.schemas.append(path)
            elif "middleware" in lower or "permission" in lower or "auth" in lower:
                result.middleware.append(path)
            elif "test" in lower or "spec" in lower:
                result.tests.append(path)
            elif path.name in {
                "package.json",
                "pyproject.toml",
                "requirements.txt",
                "pom.xml",
                "build.gradle",
                "go.mod",
                "composer.json",
                "Gemfile",
            }:
                result.config_files.append(path)
            else:
                result.unknown.append(path)

        return result

    def build_maps(self, scan_result: ScanResult) -> Dict[str, Any]:
        return {
            "_project_path": str(scan_result.project_path),
            "file_map": {
                str(path.relative_to(scan_result.project_path)): str(path)
                for path in (
                    scan_result.routes
                    + scan_result.controllers
                    + scan_result.services
                    + scan_result.models
                    + scan_result.schemas
                    + scan_result.middleware
                    + scan_result.tests
                )
            },
            "route_map": self._name_map(scan_result.routes),
            "controller_map": self._name_map(scan_result.controllers),
            "service_map": self._name_map(scan_result.services),
            "model_map": self._name_map(scan_result.models),
            "schema_map": self._name_map(scan_result.schemas),
            "middleware_map": self._name_map(scan_result.middleware),
            "test_map": self._name_map(scan_result.tests),
        }

    def extract_genome(self, maps: Dict[str, Any], scan_result: ScanResult) -> APIGenome:
        confidence = 0.0
        confidence += 0.20 if scan_result.routes else 0
        confidence += 0.20 if scan_result.controllers else 0
        confidence += 0.20 if scan_result.services else 0
        confidence += 0.15 if scan_result.models else 0
        confidence += 0.15 if scan_result.schemas else 0
        confidence += 0.10 if scan_result.tests else 0

        return APIGenome(
            framework=self.name,
            route_style="detected" if scan_result.routes else "unknown",
            controller_style="detected" if scan_result.controllers else "unknown",
            service_style="detected" if scan_result.services else "unknown",
            model_style="detected" if scan_result.models else "unknown",
            schema_style="detected" if scan_result.schemas else "unknown",
            auth_style="detected" if scan_result.middleware else "unknown",
            test_style="detected" if scan_result.tests else "unknown",
            confidence=round(confidence, 2),
        )

    def plan_api(self, request: str, genome: APIGenome, maps: Dict[str, Any]) -> APIPlan:
        intent = IntentPlanner().plan(request)

        generation_allowed = genome.confidence >= 0.45
        reason = None if generation_allowed else "Architecture confidence too low; returning plan only."

        return APIPlan(
            request=request,
            method=intent.method,
            path=intent.path,
            entities=intent.entities,
            layers=["route", "controller", "service", "schema", "test"],
            generation_allowed=generation_allowed,
            reason=reason,
            metadata={
                "adapter": self.name,
                "resource": intent.resource,
                "action": intent.action,
                "response_status": intent.response_status,
                **intent.metadata,
            },
        )

    def generate_code(
        self,
        plan: APIPlan,
        genome: APIGenome,
        maps: Dict[str, Any],
    ) -> List[GeneratedFile]:
        if not plan.generation_allowed:
            return []

        entity = plan.entities[-1] if plan.entities else "Resource"
        lower = entity.lower()

        return [
            GeneratedFile(
                path=Path(f"generated/{lower}_api.txt"),
                content=(
                    "# Generated API plan\n"
                    f"method: {plan.method}\n"
                    f"path: {plan.path}\n"
                    f"entity: {entity}\n"
                    "note: Generic framework fallback was used.\n"
                ),
            )
        ]

    def validate_generated_code(
        self,
        files: List[GeneratedFile],
        plan: APIPlan,
        genome: APIGenome,
    ) -> ValidationReport:
        errors = []
        warnings = []

        if not plan.generation_allowed:
            errors.append(plan.reason or "Generation not allowed.")

        if plan.generation_allowed and not files:
            errors.append("No files generated.")

        for file in files:
            if not file.content.strip():
                errors.append(f"Generated file is empty: {file.path}")

        return ValidationReport(success=not errors, errors=errors, warnings=warnings)

    def _walk_files(self, root: Path) -> List[Path]:
        files = []
        root = Path(root)

        for path in root.rglob("*"):
            if path.is_dir():
                continue

            try:
                rel_parts = path.relative_to(root).parts
            except ValueError:
                rel_parts = path.parts

            if any(part in IGNORED_DIRS for part in rel_parts):
                continue

            files.append(path)

        return files

    def _name_map(self, paths: List[Path]) -> Dict[str, str]:
        return {path.stem: str(path) for path in paths}
