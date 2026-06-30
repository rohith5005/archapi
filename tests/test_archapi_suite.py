import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from archapi import ArchAPI


# ===========================================================================
# Project factory helpers
# ===========================================================================

def create_express_project(root: Path) -> Path:
    project = root / "express_basic"

    (project / "src/routes").mkdir(parents=True, exist_ok=True)
    (project / "src/controllers").mkdir(parents=True, exist_ok=True)
    (project / "src/services").mkdir(parents=True, exist_ok=True)
    (project / "src/schemas").mkdir(parents=True, exist_ok=True)
    (project / "src/models").mkdir(parents=True, exist_ok=True)
    (project / "src/middleware").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)

    (project / "package.json").write_text(
        '{"dependencies": {"express": "^4.18.0", "zod": "^3.0.0"}, '
        '"devDependencies": {"jest": "^29.0.0", "supertest": "^6.0.0"}}'
    )

    (project / "src/routes/user.routes.ts").write_text(
        'import { Router } from "express";\n'
        'import { userController } from "../controllers/user.controller";\n\n'
        'const router = Router();\n'
        'router.get("/users/:id", userController.handle);\n'
        'export default router;\n'
    )

    (project / "src/controllers/user.controller.ts").write_text(
        'import { Request, Response, NextFunction } from "express";\n\n'
        'export const userController = {\n'
        '  async handle(req: Request, res: Response, next: NextFunction) {\n'
        '    return res.status(200).json({ data: {} });\n'
        '  },\n'
        '};\n'
    )

    (project / "src/services/user.service.ts").write_text(
        'export const userService = {\n'
        '  async execute() {\n'
        '    return {};\n'
        '  },\n'
        '};\n'
    )

    (project / "src/schemas/user.schema.ts").write_text(
        'import { z } from "zod";\n'
        'export const userRequestSchema = z.object({});\n'
    )

    (project / "src/models/user.model.ts").write_text(
        'export interface User { id: string; }\n'
    )

    (project / "src/middleware/auth.middleware.ts").write_text(
        'export function requireAuth(req: unknown, res: unknown, next: () => void) {\n'
        '  next();\n'
        '}\n'
    )

    (project / "tests/user.test.ts").write_text(
        'describe("user", () => {\n'
        '  it("works", () => {\n'
        '    expect(true).toBe(true);\n'
        '  });\n'
        '});\n'
    )

    return project


def create_fastapi_project(root: Path) -> Path:
    project = root / "fastapi_basic"

    (project / "app/routers").mkdir(parents=True, exist_ok=True)
    (project / "app/services").mkdir(parents=True, exist_ok=True)
    (project / "app/schemas").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)

    (project / "requirements.txt").write_text("fastapi\npydantic\npytest\n")

    (project / "app/__init__.py").write_text("")
    (project / "app/routers/__init__.py").write_text("")
    (project / "app/services/__init__.py").write_text("")
    (project / "app/schemas/__init__.py").write_text("")

    (project / "app/routers/user_router.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        '@router.get("/users/{id}")\n'
        "async def get_user(id: str):\n"
        "    return {'id': id}\n"
    )

    (project / "app/services/user_service.py").write_text(
        "class UserService:\n"
        "    async def execute(self):\n"
        "        return {}\n\n"
        "user_service = UserService()\n"
    )

    (project / "app/schemas/user_schema.py").write_text(
        "from pydantic import BaseModel\n\n"
        "class UserResponse(BaseModel):\n"
        "    id: str\n"
    )

    (project / "tests/test_user.py").write_text(
        "def test_user_placeholder():\n"
        "    assert True\n"
    )

    return project


def create_flask_project(root: Path) -> Path:
    project = root / "flask_basic"

    (project / "app/routes").mkdir(parents=True, exist_ok=True)
    (project / "app/services").mkdir(parents=True, exist_ok=True)
    (project / "app/schemas").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)

    (project / "requirements.txt").write_text("flask\nmarshmallow\npytest\n")

    (project / "app/__init__.py").write_text("")
    (project / "app/routes/__init__.py").write_text("")
    (project / "app/services/__init__.py").write_text("")
    (project / "app/schemas/__init__.py").write_text("")

    (project / "app/routes/user_routes.py").write_text(
        "from flask import Blueprint, jsonify\n\n"
        "user_bp = Blueprint('user', __name__)\n\n"
        "@user_bp.route('/users/<user_id>', methods=['GET'])\n"
        "def get_user(user_id):\n"
        "    return jsonify({'id': user_id})\n"
    )

    (project / "app/services/user_service.py").write_text(
        "class UserService:\n"
        "    def execute(self, payload):\n"
        "        return {}\n\n"
        "user_service = UserService()\n"
    )

    (project / "app/schemas/user_schema.py").write_text(
        "from marshmallow import Schema, fields\n\n"
        "class UserSchema(Schema):\n"
        "    id = fields.Str()\n"
    )

    (project / "tests/test_user.py").write_text(
        "def test_user_placeholder():\n"
        "    assert True\n"
    )

    return project


def create_nestjs_project(root: Path) -> Path:
    project = root / "nestjs_basic"

    (project / "src/user").mkdir(parents=True, exist_ok=True)
    (project / "test").mkdir(parents=True, exist_ok=True)

    (project / "package.json").write_text(json.dumps({
        "dependencies": {
            "@nestjs/common": "^10.0.0",
            "@nestjs/core": "^10.0.0",
            "class-validator": "^0.14.0",
        },
        "devDependencies": {
            "jest": "^29.0.0",
            "@nestjs/testing": "^10.0.0",
        },
    }))

    (project / "src/user/user.controller.ts").write_text(
        'import { Controller, Get } from "@nestjs/common";\n\n'
        "@Controller('users')\n"
        "export class UserController {\n"
        "  @Get()\n"
        "  findAll() { return []; }\n"
        "}\n"
    )

    (project / "src/user/user.service.ts").write_text(
        'import { Injectable } from "@nestjs/common";\n\n'
        "@Injectable()\n"
        "export class UserService {\n"
        "  findAll() { return []; }\n"
        "}\n"
    )

    (project / "src/user/user.module.ts").write_text(
        'import { Module } from "@nestjs/common";\n\n'
        "@Module({ controllers: [], providers: [] })\n"
        "export class UserModule {}\n"
    )

    (project / "src/user/user.dto.ts").write_text(
        "export class UserDto { payload?: Record<string, unknown>; }\n"
    )

    (project / "test/user.spec.ts").write_text(
        "describe('User', () => { it('works', () => expect(true).toBe(true)); });\n"
    )

    return project


def create_django_drf_project(root: Path) -> Path:
    project = root / "django_basic"

    (project / "api").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)

    (project / "manage.py").write_text(
        "#!/usr/bin/env python\nimport sys\n\nif __name__ == '__main__':\n    pass\n"
    )

    (project / "requirements.txt").write_text(
        "django\ndjangorestframework\npytest\npytest-django\n"
    )

    (project / "api/views.py").write_text(
        "from rest_framework.views import APIView\n"
        "from rest_framework.response import Response\n\n"
        "class UserView(APIView):\n"
        "    def get(self, request):\n"
        "        return Response({'users': []})\n"
    )

    (project / "api/serializers.py").write_text(
        "from rest_framework import serializers\n\n"
        "class UserSerializer(serializers.Serializer):\n"
        "    id = serializers.CharField()\n"
    )

    (project / "api/urls.py").write_text(
        "from django.urls import path\n"
        "from .views import UserView\n\n"
        "urlpatterns = [path('users/', UserView.as_view())]\n"
    )

    (project / "tests/test_user.py").write_text(
        "def test_placeholder():\n"
        "    assert True\n"
    )

    return project


# ===========================================================================
# Express TypeScript
# ===========================================================================

class TestExpressGeneration(unittest.TestCase):
    def test_express_detection_and_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_express_project(Path(tmp))
            engine = ArchAPI(str(project))

            detection = engine.detect_framework()
            result = engine.generate_api("Create POST API for product review", dry_run=True)
            score = engine.score_architecture(result)

            self.assertEqual(detection.framework, "express-typescript")
            self.assertTrue(result.validation_report.success, result.validation_report.errors)
            self.assertEqual(result.plan.method, "POST")
            self.assertEqual(result.plan.path, "/products/{product_id}/reviews")
            self.assertEqual(len(result.files), 5)
            self.assertEqual(score.percentage, 100.0)
            self.assertIn('router.post("/products/:productId/reviews"', result.files[0].content)


# ===========================================================================
# FastAPI
# ===========================================================================

class TestFastAPIGeneration(unittest.TestCase):
    def test_fastapi_detection_and_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_fastapi_project(Path(tmp))
            engine = ArchAPI(str(project))

            detection = engine.detect_framework()
            result = engine.generate_api("Create GET API for payment status", dry_run=True)
            score = engine.score_architecture(result)

            self.assertEqual(detection.framework, "fastapi")
            self.assertTrue(result.validation_report.success, result.validation_report.errors)
            self.assertEqual(result.plan.method, "GET")
            self.assertEqual(result.plan.path, "/payments/{id}/status")
            self.assertEqual(len(result.files), 4)
            self.assertEqual(score.percentage, 100.0)
            self.assertIn('@router.get("/payments/{id}/status"', result.files[0].content)


# ===========================================================================
# Flask
# ===========================================================================

class TestFlaskGeneration(unittest.TestCase):
    def test_flask_detection_and_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_flask_project(Path(tmp))
            engine = ArchAPI(str(project))

            detection = engine.detect_framework()
            self.assertEqual(detection.framework, "flask")

            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertTrue(result.validation_report.success, result.validation_report.errors)
            self.assertEqual(result.plan.method, "POST")
            self.assertEqual(len(result.files), 4)

            route_content = result.files[0].content
            self.assertIn("Blueprint", route_content)

    def test_flask_schema_marshmallow_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_flask_project(Path(tmp))
            engine = ArchAPI(str(project))
            genome = engine.extract_genome()
            self.assertEqual(genome.schema_style, "marshmallow")


# ===========================================================================
# NestJS
# ===========================================================================

class TestNestJSGeneration(unittest.TestCase):
    def test_nestjs_detection_and_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_nestjs_project(Path(tmp))
            engine = ArchAPI(str(project))

            detection = engine.detect_framework()
            self.assertEqual(detection.framework, "nestjs")

            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertTrue(result.validation_report.success, result.validation_report.errors)
            self.assertEqual(result.plan.method, "POST")
            self.assertEqual(len(result.files), 5)

            controller_content = result.files[0].content
            self.assertIn("@Controller(", controller_content)
            self.assertIn("@Post(", controller_content)

    def test_nestjs_module_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_nestjs_project(Path(tmp))
            engine = ArchAPI(str(project))
            result = engine.generate_api("Create GET API for user orders", dry_run=True)

            paths = [str(f.path) for f in result.files]
            self.assertTrue(any(".module.ts" in p for p in paths))

    def test_nestjs_dto_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_nestjs_project(Path(tmp))
            engine = ArchAPI(str(project))
            result = engine.generate_api("Create GET API for user orders", dry_run=True)

            paths = [str(f.path) for f in result.files]
            self.assertTrue(any(".dto.ts" in p for p in paths))


# ===========================================================================
# Django REST Framework
# ===========================================================================

class TestDjangoDRFGeneration(unittest.TestCase):
    def test_drf_detection_and_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_django_drf_project(Path(tmp))
            engine = ArchAPI(str(project))

            detection = engine.detect_framework()
            self.assertEqual(detection.framework, "django-drf")

            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertTrue(result.validation_report.success, result.validation_report.errors)
            self.assertEqual(result.plan.method, "POST")
            self.assertEqual(len(result.files), 4)

    def test_drf_serializer_and_urls_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_django_drf_project(Path(tmp))
            engine = ArchAPI(str(project))
            result = engine.generate_api("Create GET API for user orders", dry_run=True)

            names = [Path(f.path).name for f in result.files]
            self.assertIn("serializers.py", names)
            self.assertIn("urls.py", names)
            self.assertIn("views.py", names)

            url_file = next(f for f in result.files if Path(f.path).name == "urls.py")
            self.assertIn("urlpatterns", url_file.content)


# ===========================================================================
# Strict config mode
# ===========================================================================

class TestStrictConfigMode(unittest.TestCase):
    def test_express_strict_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_express_project(Path(tmp))

            engine = ArchAPI(
                str(project.parent),
                framework="express-typescript",
                config={
                    "route_dir": f"{project.name}/src/routes",
                    "controller_dir": f"{project.name}/src/controllers",
                    "service_dir": f"{project.name}/src/services",
                    "model_dir": f"{project.name}/src/models",
                    "schema_dir": f"{project.name}/src/schemas",
                    "middleware_dir": f"{project.name}/src/middleware",
                    "test_dir": f"{project.name}/tests",
                },
            )

            scan = engine.scan()
            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertEqual(len(scan.unknown), 0)
            self.assertTrue(result.validation_report.success, result.validation_report.errors)

    def test_fastapi_strict_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_fastapi_project(Path(tmp))

            engine = ArchAPI(
                str(project.parent),
                framework="fastapi",
                config={
                    "route_dir": f"{project.name}/app/routers",
                    "service_dir": f"{project.name}/app/services",
                    "schema_dir": f"{project.name}/app/schemas",
                    "test_dir": f"{project.name}/tests",
                },
            )

            scan = engine.scan()
            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertEqual(len(scan.unknown), 0)
            self.assertTrue(result.validation_report.success, result.validation_report.errors)


# ===========================================================================
# Safety and utilities
# ===========================================================================

class TestSafetyAndUtilities(unittest.TestCase):
    def test_low_confidence_project_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_project = Path(tmp) / "empty_project"
            empty_project.mkdir()

            engine = ArchAPI(str(empty_project))
            plan = engine.plan_api("Create GET API for user order history")
            result = engine.generate_api("Create GET API for user order history", dry_run=True)

            self.assertFalse(plan.generation_allowed)
            self.assertEqual(result.files, [])
            self.assertFalse(result.validation_report.success)
            self.assertTrue(
                "Framework could not be confidently detected" in plan.reason
                or "Architecture confidence too low" in plan.reason
            )

    def test_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_express_project(Path(tmp))
            engine = ArchAPI(str(project))

            redacted = engine.redact_context(
                'API_KEY="1234567890abcdef" TOKEN="abcdef1234567890" SECRET="abcdef1234567890"'
            )

            self.assertIn("[REDACTED_API_KEY]", redacted)
            self.assertIn("[REDACTED_TOKEN]", redacted)
            self.assertIn("[REDACTED_SECRET]", redacted)

    def test_policy_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_express_project(Path(tmp))
            engine = ArchAPI(str(project))

            result = engine.generate_api("Create GET API for payment status", dry_run=True)
            policy = engine.validate_policy(result)

            self.assertTrue(policy.allowed)
            self.assertEqual(policy.errors, [])


# ===========================================================================
# LLM layer — unit tests (mocked, no real API calls)
# ===========================================================================

class TestLLMLayer(unittest.TestCase):
    """Tests for the LLM path using a mocked provider — no real API calls."""

    def _make_llm_response(self, method="POST", path="/products/{product_id}/reviews"):
        return json.dumps({
            "method": method,
            "path": path,
            "entities": ["review"],
            "layers": ["route", "service", "schema", "test"],
            "files": [
                {
                    "path": "app/routers/review_router.py",
                    "content": (
                        "from fastapi import APIRouter\n"
                        "router = APIRouter()\n\n"
                        f'@router.{method.lower()}("{path}")\n'
                        "async def handle_review():\n"
                        "    return {'ok': True}\n"
                    ),
                },
                {
                    "path": "app/services/review_service.py",
                    "content": "class ReviewService:\n    async def execute(self): return {}\n",
                },
                {
                    "path": "app/schemas/review_schema.py",
                    "content": "from pydantic import BaseModel\nclass ReviewResponse(BaseModel):\n    ok: bool\n",
                },
                {
                    "path": "tests/test_review.py",
                    "content": "def test_review(): assert True\n",
                },
            ],
            "reason": "Generated by mocked LLM for unit testing",
        })

    def test_llm_path_returns_generation_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_fastapi_project(Path(tmp))

            mock_provider = MagicMock()
            mock_provider.complete.return_value = self._make_llm_response()

            engine = ArchAPI(str(project), use_llm=True, llm_provider=mock_provider)
            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertEqual(len(result.files), 4)
            self.assertEqual(result.plan.method, "POST")
            self.assertEqual(result.plan.path, "/products/{product_id}/reviews")
            mock_provider.complete.assert_called_once()

    def test_llm_provider_error_returns_blocked_result(self):
        from archapi.llm.errors import LLMProviderError

        with tempfile.TemporaryDirectory() as tmp:
            project = create_fastapi_project(Path(tmp))

            mock_provider = MagicMock()
            mock_provider.complete.side_effect = LLMProviderError("API key missing")

            engine = ArchAPI(str(project), use_llm=True, llm_provider=mock_provider)
            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertFalse(result.validation_report.success)
            self.assertEqual(result.files, [])
            self.assertFalse(result.plan.generation_allowed)

    def test_llm_parse_error_returns_blocked_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_fastapi_project(Path(tmp))

            mock_provider = MagicMock()
            mock_provider.complete.return_value = "this is not valid json {{{"

            engine = ArchAPI(str(project), use_llm=True, llm_provider=mock_provider)
            result = engine.generate_api("Create POST API for product review", dry_run=True)

            self.assertFalse(result.validation_report.success)
            self.assertEqual(result.files, [])

    def test_response_parser_strips_markdown_fences(self):
        from archapi.llm.response_parser import ResponseParser

        raw = "```json\n" + self._make_llm_response() + "\n```"
        plan, files = ResponseParser().parse(raw)

        self.assertEqual(plan.method, "POST")
        self.assertEqual(len(files), 4)

    def test_prompt_builder_includes_genome_info(self):
        from archapi.llm.prompt_builder import PromptBuilder
        from archapi.types import APIGenome

        genome = APIGenome(
            framework="fastapi",
            route_style="fastapi-apirouter",
            schema_style="pydantic",
            confidence=0.85,
        )

        prompt = PromptBuilder().build("Create GET API for user orders", genome)

        self.assertIn("fastapi", prompt)
        self.assertIn("fastapi-apirouter", prompt)
        self.assertIn("pydantic", prompt)
        self.assertIn("GET API for user orders", prompt)

    def test_deterministic_path_unchanged_when_use_llm_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_fastapi_project(Path(tmp))

            engine = ArchAPI(str(project), use_llm=False)
            result = engine.generate_api("Create GET API for payment status", dry_run=True)

            self.assertEqual(len(result.files), 4)
            self.assertTrue(result.validation_report.success)


if __name__ == "__main__":
    unittest.main()
