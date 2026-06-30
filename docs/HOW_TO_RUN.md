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

For Express TypeScript, ArchAPI can generate:

- route files
- controller files
- service files
- schema files
- test files

For FastAPI, ArchAPI can generate:

- router files
- service files
- schema files
- test files

ArchAPI supports dry-run generation, which means users can inspect generated files before writing anything to disk.

---

## 2. Requirements

Before using ArchAPI, make sure Python is installed.

Recommended Python version:

```text
Python 3.9 or higher
```

Check Python:

```bash
python3 --version
```

Some systems use `python` instead of `python3`:

```bash
python --version
```

If plain `pip` does not work, use:

```bash
python -m pip
```

instead of:

```bash
pip
```

This guide uses `python -m pip` because it is safer and works better inside virtual environments.

---

## 3. Option 1: Install from PyPI

This is the easiest way to use ArchAPI.

Create a new virtual environment:

```bash
python3 -m venv archapi-env
```

Activate it on macOS or Linux:

```bash
source archapi-env/bin/activate
```

Activate it on Windows PowerShell:

```powershell
archapi-env\Scripts\Activate.ps1
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install ArchAPI:

```bash
python -m pip install archapi
```

Verify installation:

```bash
python -c "from archapi import ArchAPI; print('ArchAPI import works')"
```

Expected output:

```text
ArchAPI import works
```

---

## 4. Option 2: Run from GitHub Source

Use this option if you want to inspect the source code, modify ArchAPI, run the full test suite, or contribute to the project.

Clone the repository:

```bash
git clone https://github.com/rohith5005/archapi.git
cd archapi
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Upgrade build tools:

```bash
python -m pip install --upgrade pip setuptools wheel
```

Install ArchAPI in editable mode:

```bash
python -m pip install -e .
```

Editable mode means changes to source files inside the `archapi/` folder are immediately available without reinstalling the package.

Verify import:

```bash
python -c "from archapi import ArchAPI; print('GitHub source install worked')"
```

Expected output:

```text
GitHub source install worked
```

---

## 5. Run All Tests

From the cloned repository root, run:

```bash
python -m compileall archapi
python -m unittest tests.test_archapi_suite -v
```

Expected output should end with:

```text
Ran 7 tests

OK
```

The test suite checks:

- Express TypeScript detection
- Express TypeScript generation
- FastAPI detection
- FastAPI generation
- strict config mode
- low-confidence blocking
- context redaction
- policy validation
- architecture scoring

You can also use the helper script:

```bash
./scripts/run_tests.sh
```

If the script does not run because of permissions, run:

```bash
chmod +x scripts/run_tests.sh
./scripts/run_tests.sh
```

---

## 6. Basic Usage

Import ArchAPI:

```python
from archapi import ArchAPI
```

Create an engine for a backend project:

```python
engine = ArchAPI("./my_backend_project")
```

Generate an API in dry-run mode:

```python
result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=True,
)
```

Print generated output:

```python
print(result.plan)
print(result.validation_report)
print(result.diff)
```

---

## 7. What Dry Run Means

Dry-run mode means ArchAPI generates files in memory only.

It does not write files to disk.

Example:

```python
result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=True,
)
```

Use dry-run first to inspect:

```python
print(result.diff)
```

Only write files after reviewing them.

---

## 8. Writing Files to Disk

To actually create files:

```python
result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=False,
)
```

ArchAPI protects existing files.

If a generated file already exists, ArchAPI raises:

```text
FileExistsError
```

This prevents accidental overwrites.

---

## 9. Express TypeScript Example

This example creates a tiny Express TypeScript project and asks ArchAPI to generate a new API.

Run this in Python:

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
    '{"dependencies": {"express": "^4.18.0", "zod": "^3.0.0"}, '
    '"devDependencies": {"jest": "^29.0.0", "supertest": "^6.0.0"}}'
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
result = engine.generate_api(
    "Create GET API for user order history",
    dry_run=True,
)

print("Detected framework:", engine.detect_framework().framework)
print("Generated method:", result.plan.method)
print("Generated path:", result.plan.path)
print("Generated files:", [str(file.path) for file in result.files])
```

Expected output:

```text
Detected framework: express-typescript
Generated method: GET
Generated path: /users/{user_id}/orders
Generated files: ['src/routes/order.routes.ts', 'src/controllers/order.controller.ts', 'src/services/order.service.ts', 'src/schemas/order.schema.ts', 'tests/order.test.ts']
```

---

## 10. FastAPI Example

This example creates a tiny FastAPI project and asks ArchAPI to generate a new API.

Run this in Python:

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
result = engine.generate_api(
    "Create POST API for product review",
    dry_run=True,
)

print("Detected framework:", engine.detect_framework().framework)
print("Generated method:", result.plan.method)
print("Generated path:", result.plan.path)
print("Generated files:", [str(file.path) for file in result.files])
```

Expected output:

```text
Detected framework: fastapi
Generated method: POST
Generated path: /products/{product_id}/reviews
Generated files: ['app/routers/review_router.py', 'app/services/review_service.py', 'app/schemas/review_schema.py', 'tests/test_review.py']
```

---

## 11. Strict Config Mode

Use strict config mode when:

- the project has a custom folder structure
- the framework is known but automatic detection is not enough
- the repository contains multiple projects
- you only want ArchAPI to scan specific folders

Example for Express TypeScript:

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

When strict config is used, ArchAPI scans only the configured folders.

---

## 12. Low-Confidence Blocking

ArchAPI blocks generation when it cannot confidently detect the framework or architecture.

Example:

```python
from archapi import ArchAPI

engine = ArchAPI("./unknown_project")

plan = engine.plan_api("Create GET API for user order history")

print(plan.generation_allowed)
print(plan.reason)
```

Possible output:

```text
False
Framework could not be confidently detected. Provide framework or config before generation.
```

Another possible output:

```text
False
Architecture confidence too low for code generation. Missing: route style, controller style, service style, schema style
```

This prevents ArchAPI from generating files into the wrong kind of project.

---

## 13. Security Features

ArchAPI includes baseline safeguards:

- dry-run generation by default
- overwrite protection
- low-confidence blocking
- strict config mode
- generated-path policy checks
- context redaction
- secret scanning helpers

Example redaction:

```python
from archapi import ArchAPI

engine = ArchAPI("./some_project")

text = 'API_KEY="1234567890abcdef" TOKEN="abcdef1234567890"'
print(engine.redact_context(text))
```

Expected output includes:

```text
[REDACTED_API_KEY]
[REDACTED_TOKEN]
```

---

## 14. Cache and Changed Files

ArchAPI can save a snapshot of the detected project structure and later report changed files.

Example:

```python
from archapi import ArchAPI

engine = ArchAPI("./my_backend_project")

engine.scan()
engine.build_maps()
engine.extract_genome()

engine.save_cache()

print(engine.changed_files())
```

Expected immediately after saving cache:

```text
[]
```

The cache is stored inside:

```text
.archapi/
```

This folder should not be committed to Git.

---

## 15. Project Structure

The GitHub repository has this main structure:

```text
archapi/
  core.py
  types.py
  frameworks/
  planning/
  indexing/
  security/
  validation/

sample_projects/
  express_basic/
  fastapi_basic/

tests/
  test_archapi_suite.py

docs/
  HOW_TO_RUN.md
  ARCHITECTURE.md
  FILE_GUIDE.md
  SECURITY_MEASURES.md
  DEVELOPMENT_STATUS.md

scripts/
  run_tests.sh
```

---

## 16. Common Issues

### `pip: command not found`

Use:

```bash
python -m pip install archapi
```

instead of:

```bash
pip install archapi
```

---

### Editable install fails from GitHub source

Upgrade pip and setuptools:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

---

### `heredoc>` appears in terminal

This usually means markdown backticks or an unfinished heredoc were pasted into the shell.

Press:

```text
Ctrl + C
```

Then rerun only the actual shell command, without markdown fences such as triple backticks.

---

### Git clone says destination already exists

Do not clone inside a folder that already has an `archapi/` package directory.

Use a clean location:

```bash
cd /tmp
git clone https://github.com/rohith5005/archapi.git archapi-github-test
cd archapi-github-test
```

---

### Tests fail after cloning from GitHub

Make sure pip and setuptools are upgraded first:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
python -m unittest tests.test_archapi_suite -v
```

---

## 17. Maintainer Build and Publish Checks

These steps are for maintainers only.

Install build tools:

```bash
python -m pip install --upgrade build twine
```

Clean old build output:

```bash
rm -rf dist build archapi.egg-info
```

Build package:

```bash
python -m build
```

Check package:

```bash
python -m twine check dist/*
```

Expected:

```text
PASSED
```

Upload to TestPyPI:

```bash
python -m twine upload --repository testpypi dist/*
```

Upload to PyPI:

```bash
python -m twine upload dist/*
```

Use API tokens when uploading. Do not paste tokens into source files, GitHub, documentation, chat, or terminal logs that may be shared.

---

## 18. Project Links

GitHub:

```text
https://github.com/rohith5005/archapi
```

PyPI:

```text
https://pypi.org/project/archapi/
```

Install from PyPI:

```bash
python -m pip install archapi
```

Basic import:

```python
from archapi import ArchAPI
```
