from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from archapi.frameworks.base import FrameworkAdapter
from archapi.mapping.layer_classifier import LayerClassifier, _tokenize
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

    _classifier = LayerClassifier()

    _LAYER_TO_BUCKET = {
        "route": "routes",
        "controller": "controllers",
        "service": "services",
        "model": "models",
        "schema": "schemas",
        "middleware": "middleware",
        "test": "tests",
        "config": "config_files",
    }

    def detect(self, project_path: Path) -> DetectionResult:
        return DetectionResult("generic", 0.10, ["Fallback generic adapter"])

    def scan(self, project_path: Path) -> ScanResult:
        project_path = Path(project_path)
        result = ScanResult(framework=self.name, project_path=project_path)

        for path in self._walk_files(project_path):
            try:
                relative = path.relative_to(project_path)
            except ValueError:
                relative = Path(path.name)

            classification = self._classifier.classify(relative, framework=self.name)
            bucket_name = self._LAYER_TO_BUCKET.get(classification.layer)

            if bucket_name is not None:
                getattr(result, bucket_name).append(path)
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
        scan: Optional[ScanResult] = None,
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

        warnings.extend(self._layer_naming_consistency_warnings(files, scan))

        return ValidationReport(success=not errors, errors=errors, warnings=warnings)

    # ------------------------------------------------------------------
    # Shared validation helpers (used by all concrete framework adapters)
    # ------------------------------------------------------------------

    def _safe_classify(self, path: Path):
        """
        LayerClassifier requires a project-relative path and raises on
        anything else. Generated file paths reach this validator *before*
        PolicyGate rejects malformed/adversarial ones (e.g. an absolute
        path), so classification here must degrade to "doesn't match any
        layer" rather than raise -- PolicyGate remains the actual gate for
        those cases; this only decides layer-presence/naming checks.
        """
        try:
            return self._classifier.classify(path, framework=self.name)
        except ValueError:
            return None

    def _has_generated_layer(self, files: List[GeneratedFile], layer: str) -> bool:
        """
        Whether any generated file classifies into the given architectural
        layer, per the same LayerClassifier used for repository indexing
        (Phase 7B) -- token-based, so it recognizes the realistic naming
        variants a layer can legitimately take (e.g. test_x.py, x_test.py,
        x.spec.ts, or a bare tests.py) instead of one hardcoded pattern.
        """
        for file in files:
            classification = self._safe_classify(Path(file.path))
            if classification is not None and classification.layer == layer:
                return True
        return False

    def _layer_naming_consistency_warnings(
        self,
        files: List[GeneratedFile],
        scan: Optional[ScanResult],
    ) -> List[str]:
        """
        Non-blocking evidence-based check: when the repository already has
        files for a generated file's layer, flag (warn, don't reject) if
        the new file shares no naming token with any of them -- e.g. every
        existing route file ends in `_router.py` but the generated one
        doesn't. No repository evidence for that layer yet (a project's
        first file of a kind) means nothing to compare against, so no
        warning is possible or expected.
        """
        if scan is None:
            return []

        bucket_by_layer = {
            "route": scan.routes,
            "controller": scan.controllers,
            "service": scan.services,
            "schema": scan.schemas,
            "model": scan.models,
            "test": scan.tests,
        }

        warnings: List[str] = []
        for file in files:
            classification = self._safe_classify(Path(file.path))
            if classification is None:
                continue
            existing = bucket_by_layer.get(classification.layer)
            if not existing:
                continue

            new_tokens = set(_tokenize(Path(file.path).stem))
            shares_token = any(
                new_tokens & set(_tokenize(Path(existing_path).stem))
                for existing_path in existing
            )
            if not shares_token:
                warnings.append(
                    f"Generated {classification.layer} file '{file.path}' shares no "
                    f"naming token with any existing {classification.layer} file in "
                    "this project; verify it matches the project's naming convention."
                )

        return warnings

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
