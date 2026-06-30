#!/usr/bin/env bash
set -euo pipefail

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: OPENAI_API_KEY is required."
  echo "Run: export OPENAI_API_KEY='your-real-key'"
  exit 1
fi

MODEL="${ARCHAPI_LLM_MODEL:-gpt-5-mini}"

echo "Running real OpenAI LLM smoke test with model: ${MODEL}"

python - <<'PY'
from pathlib import Path
import os
import shutil

from archapi import ArchAPI

project = Path("/tmp/archapi-openai-smoke-express")

if project.exists():
    shutil.rmtree(project)

(project / "src/routes").mkdir(parents=True, exist_ok=True)
(project / "src/controllers").mkdir(parents=True, exist_ok=True)
(project / "src/services").mkdir(parents=True, exist_ok=True)
(project / "src/schemas").mkdir(parents=True, exist_ok=True)
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
    'import { Request, Response, NextFunction } from "express";\n'
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

(project / "tests/user.test.ts").write_text(
    'describe("user", () => { it("works", () => expect(true).toBe(true)); });\n'
)

engine = ArchAPI(
    str(project),
    use_llm=True,
    llm_model=os.getenv("ARCHAPI_LLM_MODEL", "gpt-5-mini"),
)

result = engine.generate_api(
    "Create authenticated POST API for user refund request with request validation and a placeholder service",
    dry_run=True,
)

print("Detected framework:", engine.detect_framework().framework)
print("Plan:", result.plan)
print("Validation:", result.validation_report)
print("Generated files:", [str(file.path) for file in result.files])

if not result.files:
    raise SystemExit("LLM smoke test failed: no files generated.")

if not result.validation_report.success:
    raise SystemExit(f"LLM smoke test failed validation: {result.validation_report.errors}")

print("Real OpenAI LLM smoke test passed.")
PY
