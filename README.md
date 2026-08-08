# ArchAPI

ArchAPI is a Python library for architecture-preserving REST API generation.

It scans an existing backend project, detects the framework, understands the project structure, plans a REST API, generates framework-specific files, validates the output, and writes files only when explicitly requested.

## Current Status

Current checkpoint: **0.5.0**

ArchAPI currently supports:

- Express TypeScript
- FastAPI
- Flask
- Django REST Framework
- NestJS
- Generic fallback detection for unsupported projects

Core features:

- Framework detection
- Project scanning
- API architecture modeling
- Confidence scoring
- Low-confidence blocking
- Strict config mode
- REST intent planning
- Dry-run code generation
- Safe apply behavior
- Overwrite protection
- Cache and changed-file detection
- Command-line interface (`archapi detect|scan|plan|generate`)
- LLM-first generation mode (optional, OpenAI-backed)
- Secret scanning helpers
- Context redaction before any LLM call
- Output safety policy gate (path traversal, absolute paths, protected
  directories, bootstrap/config files, unrequested middleware, secret-shaped
  content)
- Architecture consistency scoring
- Unified regression test suite

## Installation from PyPI

```bash
python -m pip install archapi
```

To use LLM-first generation mode, install the optional `openai` extra:

```bash
python -m pip install "archapi[openai]"
```

Verify:

```bash
python -c "from archapi import ArchAPI; print('ArchAPI import works')"
```

## Run from GitHub Source

```bash
git clone https://github.com/rohith5005/archapi.git
cd archapi

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

Verify:

```bash
python -c "from archapi import ArchAPI; print('GitHub source install worked')"
```

## Run Tests

```bash
python -m compileall archapi
python -m unittest tests.test_archapi_suite -v
```

Or:

```bash
./scripts/run_tests.sh
```

Expected result:

```text
Ran 32 tests

OK
```

## Basic Usage

```python
from archapi import ArchAPI

engine = ArchAPI("./sample_projects/express_basic")

result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=True,
)

print(result.plan)
print(result.validation_report)
print(result.diff)
```

## Command-Line Interface

```bash
archapi detect ./sample_projects/express_basic
archapi scan ./sample_projects/express_basic
archapi plan ./sample_projects/express_basic "Create GET API for user order history"
archapi generate ./sample_projects/express_basic "Create GET API for user order history"

# Write files to disk instead of a dry run
archapi generate ./sample_projects/express_basic "Create GET API for user order history" --apply
```

## LLM-First Generation (optional)

With the `openai` extra installed and `OPENAI_API_KEY` set, ArchAPI can use an
LLM to generate architecture-matching code instead of the deterministic
templates. See [LLM Usage Guide](docs/LLM_USAGE.md) for the full walkthrough.

```python
from archapi import ArchAPI

engine = ArchAPI(
    "./sample_projects/express_basic",
    use_llm=True,
    llm_model="gpt-4o-mini",
)

result = engine.generate_api(
    "Create authenticated POST API for user refund request",
    dry_run=True,
)

print(result.plan)
print(result.validation_report)
```

Deterministic generation (`use_llm=False`, the default) does not require the
`openai` package and works fully offline.

## Express TypeScript Example

```python
from pathlib import Path
from archapi import ArchAPI

project = Path("express_basic")

(project / "src/routes").mkdir(parents=True, exist_ok=True)
(project / "src/controllers").mkdir(parents=True, exist_ok=True)
(project / "src/services").mkdir(parents=True, exist_ok=True)
(project / "src/schemas").mkdir(parents=True, exist_ok=True)
(project / "tests").mkdir(parents=True, exist_ok=True)

(project / "package.json").write_text(
    '{"dependencies": {"express": "^4.18.0", "zod": "^3.0.0"}}'
)

(project / "src/routes/user.routes.ts").write_text(
    'import { Router } from "express";\n'
    'const router = Router();\n'
    'export default router;\n'
)

(project / "src/controllers/user.controller.ts").write_text(
    'export const userController = {};\n'
)

(project / "src/services/user.service.ts").write_text(
    'export const userService = {};\n'
)

(project / "src/schemas/user.schema.ts").write_text(
    'import { z } from "zod";\n'
)

(project / "tests/user.test.ts").write_text(
    'describe("user", () => { it("works", () => expect(true).toBe(true)); });\n'
)

engine = ArchAPI(str(project))
result = engine.generate_api("Create GET API for user order history", dry_run=True)

print("Detected framework:", engine.detect_framework().framework)
print("Generated method:", result.plan.method)
print("Generated path:", result.plan.path)
print("Generated files:", [str(file.path) for file in result.files])
```

Expected output includes:

```text
Detected framework: express-typescript
Generated method: GET
Generated path: /users/{user_id}/orders
```

## FastAPI Example

```python
from pathlib import Path
from archapi import ArchAPI

project = Path("fastapi_basic")

(project / "app/routers").mkdir(parents=True, exist_ok=True)
(project / "app/services").mkdir(parents=True, exist_ok=True)
(project / "app/schemas").mkdir(parents=True, exist_ok=True)
(project / "tests").mkdir(parents=True, exist_ok=True)

(project / "requirements.txt").write_text("fastapi\npydantic\npytest\n")

(project / "app/routers/user_router.py").write_text(
    "from fastapi import APIRouter\n"
    "router = APIRouter()\n"
)

(project / "app/services/user_service.py").write_text(
    "class UserService:\n"
    "    pass\n\n"
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

engine = ArchAPI(str(project))
result = engine.generate_api("Create POST API for product review", dry_run=True)

print("Detected framework:", engine.detect_framework().framework)
print("Generated method:", result.plan.method)
print("Generated path:", result.plan.path)
print("Generated files:", [str(file.path) for file in result.files])
```

Expected output includes:

```text
Detected framework: fastapi
Generated method: POST
Generated path: /products/{product_id}/reviews
```

## Documentation

- [How to Run](docs/HOW_TO_RUN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [File Guide](docs/FILE_GUIDE.md)
- [Security Measures](docs/SECURITY_MEASURES.md)
- [LLM Usage Guide](docs/LLM_USAGE.md)
- [Development Status](docs/DEVELOPMENT_STATUS.md)

## Contributors

- [Rohith Chikkala](https://github.com/rohith5005)
- [Praneeth Koppolu](https://github.com/iampraneethk)

## Links

- GitHub: https://github.com/rohith5005/archapi
- PyPI: https://pypi.org/project/archapi/
