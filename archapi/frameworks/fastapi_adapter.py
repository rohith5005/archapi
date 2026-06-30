from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from archapi.frameworks.generic import GenericAdapter
from archapi.types import APIPlan, APIGenome, GeneratedFile, ScanResult, ValidationReport


class FastAPIAdapter(GenericAdapter):
    name = "fastapi"

    def scan(self, project_path: Path) -> ScanResult:
        result = super().scan(project_path)
        result.framework = self.name
        return result

    def extract_genome(self, maps: Dict[str, Any], scan_result: ScanResult) -> APIGenome:
        genome = super().extract_genome(maps, scan_result)
        genome.framework = self.name

        req = scan_result.project_path / "requirements.txt"
        pyproject = scan_result.project_path / "pyproject.toml"

        dep_text = ""
        if req.exists():
            dep_text += req.read_text(encoding="utf-8", errors="ignore").lower()
        if pyproject.exists():
            dep_text += pyproject.read_text(encoding="utf-8", errors="ignore").lower()

        genome.route_style = "fastapi-apirouter" if scan_result.routes else "unknown"
        genome.controller_style = "fastapi-endpoint" if scan_result.controllers or scan_result.routes else "unknown"
        genome.service_style = "service-layer" if scan_result.services else "unknown"
        genome.schema_style = "pydantic" if "pydantic" in dep_text or scan_result.schemas else "unknown"
        genome.test_style = "pytest" if "pytest" in dep_text or scan_result.tests else "unknown"
        genome.metadata["language"] = "python"
        genome.metadata["project_path"] = str(scan_result.project_path)

        has_fastapi_dependency = "fastapi" in dep_text

        if not scan_result.routes and not scan_result.services:
            genome.confidence = min(genome.confidence, 0.10)
        elif not has_fastapi_dependency:
            genome.confidence = min(genome.confidence, 0.65)
            genome.metadata["dependency_warning"] = "FastAPI dependency not found at project root."

        return genome

    def generate_code(
        self,
        plan: APIPlan,
        genome: APIGenome,
        maps: Dict[str, Any],
    ) -> List[GeneratedFile]:
        if not plan.generation_allowed:
            return []

        entity = plan.entities[-1] if plan.entities else "Resource"
        entity_pascal = entity[0].upper() + entity[1:]
        entity_lower = entity_pascal[0].lower() + entity_pascal[1:]
        entity_file = entity_lower.lower()

        router_dir = self._output_dir(maps, "route_map", "app/routers")
        service_dir = self._output_dir(maps, "service_map", "app/services")
        schema_dir = self._output_dir(maps, "schema_map", "app/schemas")
        test_dir = self._output_dir(maps, "test_map", "tests")

        router_path = router_dir / f"{entity_file}_router.py"
        service_path = service_dir / f"{entity_file}_service.py"
        schema_path = schema_dir / f"{entity_file}_schema.py"
        test_path = test_dir / f"test_{entity_file}.py"

        method = plan.method.lower()
        status_code = int(plan.metadata.get("response_status", 200))
        action = plan.metadata.get("action", "unknown")

        router_content = f'''from fastapi import APIRouter, HTTPException
from app.schemas.{entity_file}_schema import {entity_pascal}Request, {entity_pascal}Response
from app.services.{entity_file}_service import {entity_lower}_service

router = APIRouter()


@router.{method}("{plan.path}", response_model={entity_pascal}Response, status_code={status_code})
async def handle_{entity_lower}(request: {entity_pascal}Request = None):
    try:
        result = await {entity_lower}_service.execute(request)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
'''

        service_content = f'''from app.schemas.{entity_file}_schema import {entity_pascal}Request, {entity_pascal}Response


class {entity_pascal}Service:
    async def execute(self, request: {entity_pascal}Request | None) -> {entity_pascal}Response:
        # TODO: Replace this placeholder with project-specific business logic.
        return {entity_pascal}Response(
            message="{entity_pascal} API placeholder response",
            action="{action}",
        )


{entity_lower}_service = {entity_pascal}Service()
'''

        schema_content = f'''from pydantic import BaseModel
from typing import Optional, Any, Dict


class {entity_pascal}Request(BaseModel):
    params: Optional[Dict[str, Any]] = None
    query: Optional[Dict[str, Any]] = None
    body: Optional[Any] = None


class {entity_pascal}Response(BaseModel):
    message: str
    action: str
'''

        test_content = f'''def test_{entity_lower}_generated_placeholder():
    # TODO: Replace this placeholder with a real TestClient request.
    assert True
'''

        return [
            GeneratedFile(router_path, router_content),
            GeneratedFile(service_path, service_content),
            GeneratedFile(schema_path, schema_content),
            GeneratedFile(test_path, test_content),
        ]

    def _output_dir(self, maps: Dict[str, Any], map_key: str, fallback: str) -> Path:
        values = maps.get(map_key, {})
        project_path = Path(maps.get("_project_path", "."))

        if isinstance(values, dict) and values:
            first_path = Path(next(iter(values.values()))).resolve()
            parent = first_path.parent

            try:
                return parent.relative_to(project_path)
            except ValueError:
                return Path(fallback)

        return Path(fallback)

    def validate_generated_code(
        self,
        files: List[GeneratedFile],
        plan: APIPlan,
        genome: APIGenome,
    ) -> ValidationReport:
        errors: List[str] = []
        warnings: List[str] = []

        if not plan.generation_allowed:
            errors.append(plan.reason or "Generation not allowed.")

        required_suffixes = ["_router.py", "_service.py", "_schema.py"]
        generated_paths = [str(file.path) for file in files]

        for suffix in required_suffixes:
            if not any(path.endswith(suffix) for path in generated_paths):
                errors.append(f"Missing generated FastAPI layer: {suffix}")

        if not any("/test_" in path or path.startswith("tests/test_") for path in generated_paths):
            errors.append("Missing generated FastAPI test layer.")

        for file in files:
            if not file.content.strip():
                errors.append(f"Generated file is empty: {file.path}")

            if Path(file.path).exists():
                warnings.append(
                    f"Generated file path already exists relative to current directory: {file.path}"
                )

        if genome.confidence < 0.75:
            warnings.append("Architecture confidence is moderate; review generated files before applying.")

        return ValidationReport(success=not errors, errors=errors, warnings=warnings)
