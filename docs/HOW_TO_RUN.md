# How to Run ArchAPI

This guide explains how a new user can install, run, test, and use ArchAPI.

ArchAPI can be used in two ways:

1. Install directly from PyPI.
2. Clone the GitHub repository and run it from source.

This guide uses generic paths only. It does not depend on the project creator’s local machine path.

---

## 1. What ArchAPI Is

ArchAPI is a Python library for architecture-preserving REST API generation.

It studies an existing backend project, detects the framework and project structure, plans a REST API, generates framework-specific files, validates the generated output, and writes files only when explicitly requested.

Current dedicated framework support:

- Express TypeScript
- FastAPI

ArchAPI is useful when you want to generate new API layers that follow an existing backend structure.

For Express TypeScript, ArchAPI can generate route, controller, service, schema, and test files.

For FastAPI, ArchAPI can generate router, service, schema, and test files.

ArchAPI supports dry-run generation, which means users can inspect generated files before writing anything to disk.

---

## 2. Requirements

Recommended Python version:

```text
Python 3.9 or higher
```

Check Python:

```bash
python3 --version
```

If plain `pip` does not work, use:

```bash
python -m pip
```

---

## 3. Install from PyPI

```bash
python3 -m venv archapi-env
source archapi-env/bin/activate
python -m pip install --upgrade pip
python -m pip install archapi
python -c "from archapi import ArchAPI; print('ArchAPI import works')"
```

Expected output:

```text
ArchAPI import works
```

---

## 4. Run from GitHub Source

```bash
git clone https://github.com/rohith5005/archapi.git
cd archapi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
python -c "from archapi import ArchAPI; print('GitHub source install worked')"
```

Expected output:

```text
GitHub source install worked
```

---

## 5. Run All Tests

```bash
python -m compileall archapi
python -m unittest tests.test_archapi_suite -v
```

Expected output:

```text
Ran 7 tests

OK
```

Or use:

```bash
./scripts/run_tests.sh
```

---

## 6. Basic Usage

```python
from archapi import ArchAPI

engine = ArchAPI("./my_backend_project")

result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=True,
)

print(result.plan)
print(result.validation_report)
print(result.diff)
```

---

## 7. Dry Run vs Writing Files

Dry run generates files in memory only:

```python
result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=True,
)
```

To write files to disk:

```python
result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=False,
)
```

ArchAPI raises `FileExistsError` if a generated file already exists.

---

## 8. Express TypeScript Example

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

---

## 9. FastAPI Example

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

---

## 10. Strict Config Mode

Use strict config mode when the project has a custom folder structure or the repository contains multiple projects.

```python
from archapi import ArchAPI

engine = ArchAPI(
    ".",
    framework="express-typescript",
    config={
        "route_dir": "backend/src/routes",
        "controller_dir": "backend/src/controllers",
        "service_dir": "backend/src/services",
        "schema_dir": "backend/src/schemas",
        "test_dir": "backend/tests",
    },
)

result = engine.generate_api(
    "Create POST API for product review",
    dry_run=True,
)

print(result.diff)
```

---

## 11. Security Features

ArchAPI includes:

- dry-run generation by default
- overwrite protection
- low-confidence blocking
- strict config mode
- generated-path policy checks
- context redaction
- secret scanning helpers

---

## 12. Common Issues

### `pip: command not found`

Use:

```bash
python -m pip install archapi
```

### Editable install fails from GitHub source

Run:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

### `heredoc>` appears in terminal

Press `Ctrl + C`, then rerun only the actual shell command without markdown fences.

### Git clone says destination already exists

Use a clean folder:

```bash
cd /tmp
git clone https://github.com/rohith5005/archapi.git archapi-github-test
cd archapi-github-test
```

---

## 13. Links

GitHub:

```text
https://github.com/rohith5005/archapi
```

PyPI:

```text
https://pypi.org/project/archapi/
```
