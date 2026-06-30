from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from archapi.frameworks.generic import GenericAdapter
from archapi.types import APIPlan, APIGenome, GeneratedFile, ScanResult, ValidationReport


class DjangoRestFrameworkAdapter(GenericAdapter):
    name = "django-drf"

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

        has_drf = "djangorestframework" in dep_text or "rest_framework" in dep_text
        has_manage = (scan_result.project_path / "manage.py").exists()

        genome.route_style = "drf-router" if scan_result.routes else "unknown"
        genome.controller_style = "drf-viewset" if scan_result.controllers or scan_result.routes else "unknown"
        genome.service_style = "service-layer" if scan_result.services else "unknown"
        genome.schema_style = "drf-serializer" if scan_result.schemas else "unknown"
        genome.test_style = "pytest-django" if "pytest" in dep_text else "django-testcase"
        genome.metadata["language"] = "python"
        genome.metadata["project_path"] = str(scan_result.project_path)

        if not has_manage:
            genome.confidence = min(genome.confidence, 0.20)
        elif not has_drf:
            genome.confidence = min(genome.confidence, 0.55)
            genome.metadata["dependency_warning"] = "djangorestframework not found in dependencies."

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
        entity_upper = entity_lower.upper()

        app_dir = self._output_dir(maps, "route_map", f"api/{entity_file}")

        serializer_path = app_dir / "serializers.py"
        views_path = app_dir / "views.py"
        urls_path = app_dir / "urls.py"
        test_path = app_dir / "tests.py"

        serializer_content = f'''from rest_framework import serializers


class {entity_pascal}Serializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=255)
    created_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        raise NotImplementedError("Replace with {entity_pascal} model creation logic.")

    def update(self, instance, validated_data):
        raise NotImplementedError("Replace with {entity_pascal} model update logic.")
'''

        views_content = f'''from rest_framework import status, viewsets
from rest_framework.response import Response

from .serializers import {entity_pascal}Serializer


class {entity_pascal}ViewSet(viewsets.ViewSet):
    def list(self, request):
        # TODO: Replace with queryset from {entity_pascal} model.
        data = []
        serializer = {entity_pascal}Serializer(data, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = {entity_pascal}Serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        # TODO: Replace with {entity_pascal}.objects.get(pk=pk).
        return Response({{"id": pk, "name": "placeholder"}})

    def update(self, request, pk=None):
        serializer = {entity_pascal}Serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    def destroy(self, request, pk=None):
        return Response(status=status.HTTP_204_NO_CONTENT)
'''

        urls_content = f'''from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import {entity_pascal}ViewSet

router = DefaultRouter()
router.register(r"{entity_file}s", {entity_pascal}ViewSet, basename="{entity_file}")

urlpatterns = [
    path("", include(router.urls)),
]
'''

        test_content = f'''from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class {entity_pascal}APITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_{entity_file}s(self):
        url = reverse("{entity_file}-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_{entity_file}(self):
        url = reverse("{entity_file}-list")
        data = {{"name": "test {entity_lower}"}}
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST])
'''

        return [
            GeneratedFile(path=serializer_path, content=serializer_content),
            GeneratedFile(path=views_path, content=views_content),
            GeneratedFile(path=urls_path, content=urls_content),
            GeneratedFile(path=test_path, content=test_content),
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

        for f in files:
            if not f.content.strip():
                errors.append(f"Generated file is empty: {f.path}")

        if genome.metadata.get("dependency_warning"):
            warnings.append(genome.metadata["dependency_warning"])

        return ValidationReport(success=not errors, errors=errors, warnings=warnings)

    def _output_dir(self, maps: Dict[str, Any], map_key: str, default: str) -> Path:
        raw = maps.get(map_key)
        if raw and isinstance(raw, dict):
            paths = list(raw.values())
            if paths:
                return Path(paths[0]).parent
        return Path(default)
