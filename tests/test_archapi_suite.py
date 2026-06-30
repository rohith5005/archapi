import tempfile
import unittest
from pathlib import Path

from archapi import ArchAPI


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


if __name__ == "__main__":
    unittest.main()
