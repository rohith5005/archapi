"""
Phase 7F: cross-framework / cross-resource evaluation matrix.

Proves ArchAPI's retrieval pipeline generalizes across the frameworks it
supports and across resources that have no hard-coded rule anywhere
(warranty_claim in particular), rather than being accidentally tuned to the
"refund"/"invoice"/"shipment" fixtures used in earlier phases' unit tests.

For each (framework, resource) cell this produces a machine-readable
EvaluationResult and asserts on it, covering:

    framework detection -> layer classification -> resource extraction
    -> relevance ranking -> retrieval selection -> prompt inclusion
    -> irrelevant-example exclusion

No real OpenAI calls; a capturing fake provider is used to inspect the
actual outbound prompt, exactly as in Phase 7E.
"""

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock

from archapi import ArchAPI
from archapi.indexing.context_retriever import ContextRetriever
from archapi.indexing.repository_index import build_repository_index

# ===========================================================================
# Resource metadata
#
# warranty_claim is deliberately a two-word resource with no entry anywhere
# in IntentPlanner.ENTITY_RULES -- it exercises the generic fallback
# extraction path exactly like invoice/shipment/appointment, but as a
# compound noun ("warranty claim"), which IntentPlanner's fallback resolves
# to just the leading word ("Warranty"). That's expected, documented
# behavior (see Phase 7C), not a bug to route around here: this matrix
# verifies retrieval still ranks the right file top via the token overlap
# between "warranty" and the file's own entity terms ("warranty", "claim").
# ===========================================================================

RESOURCES = [
    {
        "key": "invoice", "pascal": "Invoice", "snake": "invoice", "kebab": "invoice",
        "url_plural": "invoices", "app_plural": "invoices",
        "request": "invoice", "expected_token": "invoice", "with_auth": True,
    },
    {
        "key": "shipment", "pascal": "Shipment", "snake": "shipment", "kebab": "shipment",
        "url_plural": "shipments", "app_plural": "shipments",
        "request": "shipment", "expected_token": "shipment", "with_auth": False,
    },
    {
        "key": "appointment", "pascal": "Appointment", "snake": "appointment", "kebab": "appointment",
        "url_plural": "appointments", "app_plural": "appointments",
        "request": "appointment", "expected_token": "appointment", "with_auth": False,
    },
    {
        "key": "warranty_claim", "pascal": "WarrantyClaim", "snake": "warranty_claim", "kebab": "warranty-claim",
        "url_plural": "warranty-claims", "app_plural": "warranty_claims",
        "request": "warranty claim", "expected_token": "warranty", "with_auth": True,
    },
]


# ===========================================================================
# Fixture builders -- one per framework, each using that framework's own
# idiomatic layout (not a copy of Express's) and covering all 4 resources
# plus one deliberately irrelevant, alphabetically-first decoy route, to
# reproduce the exact "paths[0]" failure mode Phase 7 exists to eliminate.
# ===========================================================================

def _write_all(project: Path, files: Dict[str, str]) -> None:
    for rel_path, content in files.items():
        target = project / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def create_express_matrix_project(root: Path) -> Path:
    project = root / "matrix_express_api"
    files: Dict[str, str] = {
        "package.json": json.dumps({
            "dependencies": {"express": "^4.18.0", "zod": "^3.0.0"},
            "devDependencies": {"jest": "^29.0.0"},
        }),
        "src/routes/aaa_health.routes.ts": (
            'import { Router } from "express";\n'
            "const router = Router();\n"
            'router.get("/health", (req, res) => res.json({ status: "ok" }));\n'
            "export default router;\n"
        ),
    }
    for r in RESOURCES:
        kebab, snake = r["kebab"], r["snake"]
        auth_import = (
            'import { requireAuth } from "../middleware/auth.middleware";\n'
            if r["with_auth"] else ""
        )
        auth_arg = "requireAuth, " if r["with_auth"] else ""
        files[f"src/routes/{kebab}.routes.ts"] = (
            'import { Router } from "express";\n'
            f'import {{ {snake}Controller }} from "../controllers/{kebab}.controller";\n'
            f"{auth_import}\n"
            "const router = Router();\n"
            f'router.post("/{r["url_plural"]}", {auth_arg}{snake}Controller.handle);\n'
            "export default router;\n"
        )
        files[f"src/controllers/{kebab}.controller.ts"] = (
            f"export const {snake}Controller = {{\n"
            "  async handle(req, res) { return res.json({}); },\n"
            "};\n"
        )
        files[f"src/services/{kebab}.service.ts"] = (
            f"export const {snake}Service = {{\n"
            "  async execute() { return {}; },\n"
            "};\n"
        )
        files[f"src/schemas/{kebab}.schema.ts"] = (
            'import { z } from "zod";\n\n'
            f"export const {snake}Schema = z.object({{}});\n"
        )
        files[f"tests/{kebab}.test.ts"] = (
            f"describe('{snake}', () => {{ it('works', () => expect(true).toBe(true)); }});\n"
        )
    files["src/middleware/auth.middleware.ts"] = (
        "export function requireAuth(req, res, next) {\n  next();\n}\n"
    )
    _write_all(project, files)
    return project


def create_fastapi_matrix_project(root: Path) -> Path:
    project = root / "matrix_fastapi_api"
    files: Dict[str, str] = {
        "requirements.txt": "fastapi\npydantic\npytest\n",
        "app/routers/aaa_health_router.py": (
            "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n"
            '@router.get("/health")\n'
            "async def health_check():\n"
            "    return {'status': 'ok'}\n"
        ),
        "app/middleware/auth_middleware.py": (
            "def get_current_user():\n    return {'id': 'demo'}\n"
        ),
    }
    for r in RESOURCES:
        snake, pascal = r["snake"], r["pascal"]
        auth_import = (
            "from fastapi import Depends\n"
            "from app.middleware.auth_middleware import get_current_user\n"
            if r["with_auth"] else ""
        )
        auth_dep = ", user: dict = Depends(get_current_user)" if r["with_auth"] else ""
        files[f"app/routers/{snake}_router.py"] = (
            "from fastapi import APIRouter\n"
            f"from app.schemas.{snake}_schema import {pascal}Request, {pascal}Response\n"
            f"from app.services.{snake}_service import {snake}_service\n"
            f"{auth_import}\n"
            "router = APIRouter()\n\n"
            f'@router.post("/{r["url_plural"]}", response_model={pascal}Response)\n'
            f"async def create_{snake}(payload: {pascal}Request{auth_dep}):\n"
            f"    return await {snake}_service.execute(payload)\n"
        )
        files[f"app/services/{snake}_service.py"] = (
            f"class {pascal}Service:\n"
            "    async def execute(self, payload):\n        return {}\n\n"
            f"{snake}_service = {pascal}Service()\n"
        )
        files[f"app/schemas/{snake}_schema.py"] = (
            "from pydantic import BaseModel\n\n"
            f"class {pascal}Request(BaseModel):\n    pass\n\n"
            f"class {pascal}Response(BaseModel):\n    message: str\n"
        )
        files[f"tests/test_{snake}.py"] = f"def test_{snake}():\n    assert True\n"
    _write_all(project, files)
    return project


def create_flask_matrix_project(root: Path) -> Path:
    project = root / "matrix_flask_api"
    files: Dict[str, str] = {
        "requirements.txt": "flask\nmarshmallow\nflask-login\npytest\n",
        "app/blueprints/aaa_health_routes.py": (
            "from flask import Blueprint, jsonify\n\n"
            "health_bp = Blueprint('health', __name__)\n\n"
            "@health_bp.route('/health', methods=['GET'])\n"
            "def health_check():\n    return jsonify({'status': 'ok'})\n"
        ),
    }
    for r in RESOURCES:
        snake, pascal = r["snake"], r["pascal"]
        login_import = "from flask_login import login_required\n" if r["with_auth"] else ""
        decorator = "@login_required\n" if r["with_auth"] else ""
        files[f"app/blueprints/{snake}_routes.py"] = (
            "from flask import Blueprint, jsonify\n"
            f"{login_import}\n"
            f"{snake}_bp = Blueprint('{snake}', __name__)\n\n"
            f"{decorator}"
            f"@{snake}_bp.route('/{r['url_plural']}', methods=['POST'])\n"
            f"def create_{snake}():\n    return jsonify({{}})\n"
        )
        files[f"app/services/{snake}_service.py"] = (
            f"class {pascal}Service:\n"
            "    def execute(self, payload):\n        return {}\n\n"
            f"{snake}_service = {pascal}Service()\n"
        )
        files[f"app/schemas/{snake}_schema.py"] = (
            "from marshmallow import Schema, fields\n\n"
            f"class {pascal}Schema(Schema):\n    id = fields.Str()\n"
        )
        files[f"tests/test_{snake}.py"] = f"def test_{snake}():\n    assert True\n"
    _write_all(project, files)
    return project


def create_django_matrix_project(root: Path) -> Path:
    project = root / "matrix_django_api"
    files: Dict[str, str] = {
        "manage.py": "#!/usr/bin/env python\nif __name__ == '__main__':\n    pass\n",
        "requirements.txt": "django\ndjangorestframework\npytest\npytest-django\n",
        "health/views.py": (
            "from rest_framework.views import APIView\n"
            "from rest_framework.response import Response\n\n"
            "class HealthView(APIView):\n"
            "    def get(self, request):\n        return Response({'status': 'ok'})\n"
        ),
    }
    for r in RESOURCES:
        pascal, app = r["pascal"], r["app_plural"]
        perm_import = "from rest_framework.permissions import IsAuthenticated\n" if r["with_auth"] else ""
        perm_attr = "    permission_classes = [IsAuthenticated]\n" if r["with_auth"] else ""
        files[f"{app}/views.py"] = (
            "from rest_framework.views import APIView\n"
            "from rest_framework.response import Response\n"
            f"{perm_import}\n"
            f"class {pascal}View(APIView):\n"
            f"{perm_attr}"
            "    def post(self, request):\n        return Response({})\n"
        )
        files[f"{app}/serializers.py"] = (
            "from rest_framework import serializers\n\n"
            f"class {pascal}Serializer(serializers.Serializer):\n    id = serializers.CharField()\n"
        )
        files[f"{app}/urls.py"] = (
            "from django.urls import path\n"
            f"from .views import {pascal}View\n\n"
            f"urlpatterns = [path('{r['url_plural']}/', {pascal}View.as_view())]\n"
        )
        files[f"{app}/tests.py"] = f"def test_{r['snake']}():\n    assert True\n"
    _write_all(project, files)
    return project


def create_nestjs_matrix_project(root: Path) -> Path:
    project = root / "matrix_nestjs_api"
    files: Dict[str, str] = {
        "package.json": json.dumps({
            "dependencies": {"@nestjs/common": "^10.0.0", "@nestjs/core": "^10.0.0"},
            "devDependencies": {"jest": "^29.0.0"},
        }),
        "src/health/health.controller.ts": (
            'import { Controller, Get } from "@nestjs/common";\n\n'
            "@Controller('health')\n"
            "export class HealthController {\n"
            "  @Get()\n  check() { return { status: 'ok' }; }\n"
            "}\n"
        ),
    }
    for r in RESOURCES:
        kebab, snake, pascal = r["kebab"], r["snake"], r["pascal"]
        guard_import = (
            'import { UseGuards } from "@nestjs/common";\n'
            f'import {{ AuthGuard }} from "../auth.guard";\n' if r["with_auth"] else ""
        )
        guard_decorator = "  @UseGuards(AuthGuard)\n" if r["with_auth"] else ""
        files[f"src/{kebab}/{kebab}.controller.ts"] = (
            'import { Controller, Post, Body } from "@nestjs/common";\n'
            f"{guard_import}"
            f'import {{ {pascal}Service }} from "./{kebab}.service";\n'
            f'import {{ {pascal}Dto }} from "./{kebab}.dto";\n\n'
            f"@Controller('{r['url_plural']}')\n"
            f"export class {pascal}Controller {{\n"
            f"  constructor(private readonly {snake}Service: {pascal}Service) {{}}\n\n"
            f"{guard_decorator}"
            "  @Post()\n"
            f"  create(@Body() dto: {pascal}Dto) {{ return this.{snake}Service.create(dto); }}\n"
            "}\n"
        )
        files[f"src/{kebab}/{kebab}.service.ts"] = (
            'import { Injectable } from "@nestjs/common";\n\n'
            "@Injectable()\n"
            f"export class {pascal}Service {{\n"
            "  create(dto) { return dto; }\n"
            "}\n"
        )
        files[f"src/{kebab}/{kebab}.module.ts"] = (
            'import { Module } from "@nestjs/common";\n\n'
            f"@Module({{ controllers: [], providers: [] }})\n"
            f"export class {pascal}Module {{}}\n"
        )
        files[f"src/{kebab}/{kebab}.dto.ts"] = (
            f"export class {pascal}Dto {{ payload?: Record<string, unknown>; }}\n"
        )
        files[f"test/{kebab}.spec.ts"] = (
            f"describe('{pascal}', () => {{ it('works', () => expect(true).toBe(true)); }});\n"
        )
    _write_all(project, files)
    return project


# Framework name -> (fixture builder, expected detected framework,
# category holding the primary "route-equivalent" example, relative path
# template for that primary example, decoy filename fragment).
FRAMEWORK_MATRIX = {
    "express-typescript": {
        "build": create_express_matrix_project,
        "primary_category": "routes",
        "primary_path": lambda r: f"src/routes/{r['kebab']}.routes.ts",
        "decoy_fragment": "aaa_health",
    },
    "fastapi": {
        "build": create_fastapi_matrix_project,
        "primary_category": "routes",
        "primary_path": lambda r: f"app/routers/{r['snake']}_router.py",
        "decoy_fragment": "aaa_health",
    },
    "flask": {
        "build": create_flask_matrix_project,
        "primary_category": "routes",
        "primary_path": lambda r: f"app/blueprints/{r['snake']}_routes.py",
        "decoy_fragment": "aaa_health",
    },
    "django-drf": {
        "build": create_django_matrix_project,
        "primary_category": "controllers",
        "primary_path": lambda r: f"{r['app_plural']}/views.py",
        "decoy_fragment": "health/views.py",
    },
    "nestjs": {
        "build": create_nestjs_matrix_project,
        "primary_category": "controllers",
        "primary_path": lambda r: f"src/{r['kebab']}/{r['kebab']}.controller.ts",
        "decoy_fragment": "health.controller",
    },
}


# ===========================================================================
# Machine-readable evaluation record
# ===========================================================================

@dataclass
class EvaluationResult:
    framework: str
    request: str
    expected_resource: str
    detected_framework: str = ""
    detected_resource: str = ""
    expected_top_example: str = ""
    retrieved_examples: List[str] = field(default_factory=list)
    resource_match: bool = False
    correct_top_retrieval: bool = False
    relevant_layer_coverage: int = 0
    irrelevant_selection_count: int = 0
    deterministic: bool = False
    prompt_includes_expected: bool = False
    prompt_excludes_decoy: bool = False

    def to_dict(self) -> dict:
        return {
            "framework": self.framework,
            "request": self.request,
            "expected_resource": self.expected_resource,
            "detected_framework": self.detected_framework,
            "detected_resource": self.detected_resource,
            "expected_top_example": self.expected_top_example,
            "retrieved_examples": self.retrieved_examples,
            "resource_match": self.resource_match,
            "correct_top_retrieval": self.correct_top_retrieval,
            "relevant_layer_coverage": self.relevant_layer_coverage,
            "irrelevant_selection_count": self.irrelevant_selection_count,
            "deterministic": self.deterministic,
            "prompt_includes_expected": self.prompt_includes_expected,
            "prompt_excludes_decoy": self.prompt_excludes_decoy,
        }


def _mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = json.dumps({
        "method": "POST", "path": "/x", "entities": ["x"],
        "layers": ["route", "service", "schema", "test"],
        "files": [{"path": "generated/x.py", "content": "x = 1\n"}],
    })
    return provider


def run_case(project: Path, framework_key: str, resource: dict) -> EvaluationResult:
    spec = FRAMEWORK_MATRIX[framework_key]
    request = f"Create authenticated POST API for {resource['request']} with validation"
    result = EvaluationResult(
        framework=framework_key,
        request=request,
        expected_resource=resource["expected_token"],
        expected_top_example=spec["primary_path"](resource),
    )

    engine = ArchAPI(str(project))
    detection = engine.detect_framework()
    result.detected_framework = detection.framework

    genome = engine.extract_genome()
    scan = engine._scan or engine.scan()
    maps = engine.build_maps()
    adapter = engine._adapter()
    plan_hint = adapter.plan_api(request, genome, maps)
    result.detected_resource = (plan_hint.entities[-1].lower() if plan_hint.entities else "")
    result.resource_match = result.detected_resource == resource["expected_token"]

    index = build_repository_index(scan, genome)
    ctx1 = ContextRetriever().retrieve(request=request, plan=plan_hint, index=index)
    ctx2 = ContextRetriever().retrieve(request=request, plan=plan_hint, index=index)
    result.deterministic = (
        [(i.path, i.score) for i in ctx1.all_items()]
        == [(i.path, i.score) for i in ctx2.all_items()]
    )

    result.retrieved_examples = [i.path for i in ctx1.all_items()]

    primary_items = getattr(ctx1, spec["primary_category"])
    result.correct_top_retrieval = bool(primary_items) and primary_items[0].path == result.expected_top_example

    expected_relevant_categories = ["routes", "controllers", "services", "schemas", "tests"]
    result.relevant_layer_coverage = sum(
        1 for cat in expected_relevant_categories
        if any(resource["snake"] in item.path or resource["kebab"] in item.path or resource["app_plural"] in item.path
               for item in getattr(ctx1, cat, []))
    )

    decoy_fragment = spec["decoy_fragment"]
    result.irrelevant_selection_count = sum(
        1 for item in ctx1.all_items() if decoy_fragment in item.path
    )

    provider = _mock_provider()
    llm_engine = ArchAPI(str(project), use_llm=True, llm_provider=provider)
    llm_engine.generate_api(request, dry_run=True)
    sent_prompt = provider.complete.call_args[0][0]
    result.prompt_includes_expected = result.expected_top_example in sent_prompt
    result.prompt_excludes_decoy = decoy_fragment not in sent_prompt

    return result


class TestCrossFrameworkResourceMatrix(unittest.TestCase):
    """Builds each framework's fixture once, evaluates all 4 resources
    against it (5 frameworks x 4 resources = 20 cells)."""

    _results: List[EvaluationResult] = []

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._projects: Dict[str, Path] = {}
        for framework_key, spec in FRAMEWORK_MATRIX.items():
            cls._projects[framework_key] = spec["build"](Path(cls._tmp.name))
        cls._results = []

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run_and_record(self, framework_key: str, resource: dict) -> EvaluationResult:
        result = run_case(self._projects[framework_key], framework_key, resource)
        self.__class__._results.append(result)
        return result

    def _assert_case(self, framework_key: str, resource: dict):
        spec = FRAMEWORK_MATRIX[framework_key]
        result = self._run_and_record(framework_key, resource)

        with self.subTest(framework=framework_key, resource=resource["key"]):
            self.assertEqual(
                result.detected_framework, framework_key,
                f"framework detection failed: {result.to_dict()}",
            )
            self.assertTrue(
                result.resource_match,
                f"resource extraction mismatch: {result.to_dict()}",
            )
            self.assertTrue(
                result.correct_top_retrieval,
                f"wrong top-ranked {spec['primary_category']} example: {result.to_dict()}",
            )
            self.assertGreaterEqual(
                result.relevant_layer_coverage, 3,
                f"insufficient layer coverage: {result.to_dict()}",
            )
            self.assertEqual(
                result.irrelevant_selection_count, 0,
                f"decoy example leaked into retrieval: {result.to_dict()}",
            )
            self.assertTrue(result.deterministic, f"non-deterministic retrieval: {result.to_dict()}")
            self.assertTrue(
                result.prompt_includes_expected,
                f"expected example missing from prompt: {result.to_dict()}",
            )
            self.assertTrue(
                result.prompt_excludes_decoy,
                f"decoy example leaked into prompt: {result.to_dict()}",
            )

    # -- Express TypeScript ------------------------------------------------
    def test_express_invoice(self):
        self._assert_case("express-typescript", RESOURCES[0])

    def test_express_shipment(self):
        self._assert_case("express-typescript", RESOURCES[1])

    def test_express_appointment(self):
        self._assert_case("express-typescript", RESOURCES[2])

    def test_express_warranty_claim(self):
        self._assert_case("express-typescript", RESOURCES[3])

    # -- FastAPI -------------------------------------------------------------
    def test_fastapi_invoice(self):
        self._assert_case("fastapi", RESOURCES[0])

    def test_fastapi_shipment(self):
        self._assert_case("fastapi", RESOURCES[1])

    def test_fastapi_appointment(self):
        self._assert_case("fastapi", RESOURCES[2])

    def test_fastapi_warranty_claim(self):
        self._assert_case("fastapi", RESOURCES[3])

    # -- Flask -----------------------------------------------------------
    def test_flask_invoice(self):
        self._assert_case("flask", RESOURCES[0])

    def test_flask_shipment(self):
        self._assert_case("flask", RESOURCES[1])

    def test_flask_appointment(self):
        self._assert_case("flask", RESOURCES[2])

    def test_flask_warranty_claim(self):
        self._assert_case("flask", RESOURCES[3])

    # -- Django DRF --------------------------------------------------------
    def test_django_invoice(self):
        self._assert_case("django-drf", RESOURCES[0])

    def test_django_shipment(self):
        self._assert_case("django-drf", RESOURCES[1])

    def test_django_appointment(self):
        self._assert_case("django-drf", RESOURCES[2])

    def test_django_warranty_claim(self):
        self._assert_case("django-drf", RESOURCES[3])

    # -- NestJS ------------------------------------------------------------
    def test_nestjs_invoice(self):
        self._assert_case("nestjs", RESOURCES[0])

    def test_nestjs_shipment(self):
        self._assert_case("nestjs", RESOURCES[1])

    def test_nestjs_appointment(self):
        self._assert_case("nestjs", RESOURCES[2])

    def test_nestjs_warranty_claim(self):
        self._assert_case("nestjs", RESOURCES[3])


if __name__ == "__main__":
    unittest.main()
