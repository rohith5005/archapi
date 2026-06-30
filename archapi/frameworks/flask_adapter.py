from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from archapi.frameworks.generic import GenericAdapter
from archapi.types import APIPlan, APIGenome, GeneratedFile, ScanResult, ValidationReport


class FlaskAdapter(GenericAdapter):
    """
    Framework adapter for Flask (Python).

    Generates Blueprint-based routes, service layer, schema (Marshmallow or plain
    dataclass), and pytest tests that match the detected project conventions.
    """

    name = "flask"

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def scan(self, project_path: Path) -> ScanResult:
        result = super().scan(project_path)
        result.framework = self.name
        return result

    def extract_genome(self, maps: Dict[str, Any], scan_result: ScanResult) -> APIGenome:
        genome = super().extract_genome(maps, scan_result)
        genome.framework = self.name

        dep_text = self._dep_text(scan_result.project_path)

        genome.route_style = "flask-blueprint" if scan_result.routes else "unknown"
        genome.controller_style = "flask-view" if scan_result.controllers or scan_result.routes else "unknown"
        genome.service_style = "service-layer" if scan_result.services else "unknown"
        genome.test_style = "pytest" if ("pytest" in dep_text or scan_result.tests) else "unknown"
        genome.metadata["language"] = "python"
        genome.metadata["project_path"] = str(scan_result.project_path)

        # Schema detection: prefer marshmallow, fallback to pydantic, then plain
        if "marshmallow" in dep_text:
            genome.schema_style = "marshmallow"
        elif "pydantic" in dep_text:
            genome.schema_style = "pydantic"
        elif scan_result.schemas:
            genome.schema_style = "plain"
        else:
            genome.schema_style = "unknown"

        has_flask = "flask" in dep_text

        if not scan_result.routes and not scan_result.services:
            genome.confidence = min(genome.confidence, 0.10)
        elif not has_flask:
            genome.confidence = min(genome.confidence, 0.65)
            genome.metadata["dependency_warning"] = "Flask dependency not found at project root."

        return genome

    # ------------------------------------------------------------------
    # Code generation
    # ------------------------------------------------------------------

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
        bp_name = f"{entity_file}_bp"

        route_dir = self._output_dir(maps, "route_map", "app/routes")
        service_dir = self._output_dir(maps, "service_map", "app/services")
        schema_dir = self._output_dir(maps, "schema_map", "app/schemas")
        test_dir = self._output_dir(maps, "test_map", "tests")

        route_path = route_dir / f"{entity_file}_routes.py"
        service_path = service_dir / f"{entity_file}_service.py"
        schema_path = schema_dir / f"{entity_file}_schema.py"
        test_path = test_dir / f"test_{entity_file}.py"

        method = plan.method.upper()
        http_path = plan.path
        action = plan.metadata.get("action", "unknown")
        status_code = int(plan.metadata.get("response_status", 200))

        schema_style = genome.schema_style

        # ---- Route (Blueprint) ----------------------------------------
        route_content = f'''from flask import Blueprint, request, jsonify
from app.services.{entity_file}_service import {entity_lower}_service
from app.schemas.{entity_file}_schema import {entity_pascal}Schema

{bp_name} = Blueprint("{entity_file}", __name__)
_{entity_lower}_schema = {entity_pascal}Schema()


@{bp_name}.route("{http_path}", methods=["{method}"])
def handle_{entity_lower}():
    try:
        payload = request.get_json(silent=True) or {{}}
        result = {entity_lower}_service.execute(payload)
        return jsonify(result), {status_code}
    except Exception as exc:
        return jsonify({{"error": str(exc)}}), 500
'''

        # ---- Service --------------------------------------------------
        service_content = f'''class {entity_pascal}Service:
    def execute(self, payload: dict) -> dict:
        # TODO: Replace this placeholder with project-specific business logic.
        return {{
            "message": "{entity_pascal} API placeholder response",
            "action": "{action}",
        }}


{entity_lower}_service = {entity_pascal}Service()
'''

        # ---- Schema ---------------------------------------------------
        if schema_style == "marshmallow":
            schema_content = f'''from marshmallow import Schema, fields


class {entity_pascal}Schema(Schema):
    message = fields.Str(dump_default="{entity_pascal} response")
    action = fields.Str(dump_default="{action}")
'''
        elif schema_style == "pydantic":
            schema_content = f'''from pydantic import BaseModel
from typing import Optional, Any, Dict


class {entity_pascal}Request(BaseModel):
    payload: Optional[Dict[str, Any]] = None


class {entity_pascal}Response(BaseModel):
    message: str
    action: str


class {entity_pascal}Schema:
    pass
'''
        else:
            # Plain dataclass schema
            schema_content = f'''from dataclasses import dataclass


@dataclass
class {entity_pascal}Schema:
    message: str = "{entity_pascal} response"
    action: str = "{action}"
'''

        # ---- Test -----------------------------------------------------
        test_content = f'''def test_{entity_lower}_placeholder():
    # TODO: Replace this placeholder with a real Flask test client request.
    assert True
'''

        return [
            GeneratedFile(route_path, route_content),
            GeneratedFile(service_path, service_content),
            GeneratedFile(schema_path, schema_content),
            GeneratedFile(test_path, test_content),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

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

        required_suffixes = ["_routes.py", "_service.py", "_schema.py"]
        generated_paths = [str(file.path) for file in files]

        for suffix in required_suffixes:
            if not any(path.endswith(suffix) for path in generated_paths):
                errors.append(f"Missing generated Flask layer: {suffix}")

        if not any("/test_" in path or path.startswith("tests/test_") for path in generated_paths):
            errors.append("Missing generated Flask test layer.")

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dep_text(self, project_path: Path) -> str:
        text = ""
        for fname in ("requirements.txt", "pyproject.toml", "setup.cfg", "Pipfile"):
            p = project_path / fname
            if p.exists():
                text += p.read_text(encoding="utf-8", errors="ignore").lower()
        return text

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
