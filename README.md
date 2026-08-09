# ArchAPI

ArchAPI is a Python library and CLI for architecture-preserving REST API generation.

Instead of generating API code from a generic template or an LLM's default style, ArchAPI studies your *existing* backend project first — its framework, folder conventions, naming style, authentication and validation patterns — and generates new API layers that match it. Generation is a dry-run preview by default; nothing is written to disk unless you explicitly ask for it.

Two generation modes:

- **Deterministic** — rule-based templates, works fully offline.
- **LLM-assisted** (`--llm`) — an LLM writes the code, guided by an architecture-aware retrieval pipeline that selects and shows the model the repository examples most relevant to your specific request (not arbitrary or first-found files) — see [Architecture](docs/ARCHITECTURE.md).

Dedicated framework support: **Express TypeScript, FastAPI, Flask, Django REST Framework, NestJS** (anything else falls back to a generic, lower-confidence adapter).

Current version: **1.0.0** (see [Development Status](docs/DEVELOPMENT_STATUS.md))

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
python -m compileall archapi evaluation
python -m unittest discover -s tests -v
```

Or:

```bash
./scripts/run_tests.sh
```

Expected result:

```text
Ran 231 tests

OK
```

No `OPENAI_API_KEY` is required — the full suite never makes a real network call.

## Quickstart

```bash
pip install archapi

archapi scan .
archapi plan . "Create authenticated POST API for warranty claim"

# dry-run by default
archapi generate . "Create authenticated POST API for warranty claim"

# LLM-assisted, still dry-run -- retrieval selects the repository examples
# most relevant to this request (see docs/ARCHITECTURE.md)
archapi generate . "Create authenticated POST API for warranty claim" --llm

# explicit mutation -- always opt-in
archapi generate . "Create authenticated POST API for warranty claim" --llm --apply
```

Full CLI reference (all commands, flags, exit codes): [`docs/CLI.md`](docs/CLI.md).

## Basic Usage (Python API)

```python
from archapi import ArchAPI

engine = ArchAPI("./sample_projects/express_basic")

result = engine.generate_api(
    "Create GET API for invoice",
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
archapi plan ./sample_projects/express_basic "Create GET API for shipment status"
archapi generate ./sample_projects/express_basic "Create GET API for shipment status"

# Architecture-aware LLM generation instead of deterministic templates
archapi generate ./sample_projects/express_basic "Create GET API for shipment status" --llm

# Write files to disk instead of a dry run -- always opt-in, always explicit
archapi generate ./sample_projects/express_basic "Create GET API for shipment status" --llm --apply

# Machine-readable output for CI/tooling (any command)
archapi generate ./sample_projects/express_basic "Create GET API for shipment status" --json
```

`generate` is a dry-run preview by default; nothing is written to disk unless
`--apply` is passed. Exit codes are stable and documented: `0` success, `1`
generation/validation rejected, `2` invalid CLI usage or configuration, `3`
LLM provider failure. Pass `--debug` for full tracebacks on unexpected
errors; without it, errors are concise and never include credentials.

### Configuration

Settings resolve with precedence: explicit CLI flag > project `archapi.toml`
> environment variable > built-in default (full detail:
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)). Optional project-local
`archapi.toml`:

```toml
[archapi]
use_llm = true
strict_validation = false

[archapi.llm]
provider = "openai"
model = "gpt-4o-mini"

[archapi.retrieval]
max_chars = 12000
routes = 2
services = 2
schemas = 2
tests = 2
```

API keys are never read from `archapi.toml` (ArchAPI refuses to load a
config file containing a key-, secret-, token-, password-, or
credential-like key) -- only from the `OPENAI_API_KEY` environment
variable. Equivalent environment variables exist for every field (e.g.
`ARCHAPI_USE_LLM`, `ARCHAPI_LLM_MODEL`, `ARCHAPI_ROUTES_LIMIT`) -- see
`archapi/config.py`.

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
    "Create authenticated POST API for warranty claim",
    dry_run=True,
)

print(result.plan)
print(result.validation_report)
```

Deterministic generation (`use_llm=False`, the default) does not require the
`openai` package and works fully offline.

### How architecture-aware retrieval works

On the LLM path, ArchAPI doesn't send the model arbitrary or first-found
repository files. It indexes the project, scores every candidate file
against the specific request (resource, HTTP method, whether auth/validation
was asked for), and sends a budgeted set of the highest-relevance examples —
a route or two, a service, a schema, an auth example only if authentication
was requested, a test — labeled so the model knows what each one
demonstrates. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the
full pipeline and [`docs/RESEARCH_REPORT.md`](docs/RESEARCH_REPORT.md) for
the evidence this actually changes what gets generated.

### Safety mechanisms

Dry-run by default, atomic multi-file application with automatic rollback
on partial failure, path-traversal/absolute-path rejection, project-root
containment, protected-file/bootstrap-file controls, generated-secret
detection, framework validation, and context redaction before any content
leaves the machine. No `--skip-safety`-style bypass exists. Full detail:
[`docs/SECURITY_MEASURES.md`](docs/SECURITY_MEASURES.md).

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
- [Configuration](docs/CONFIGURATION.md)
- [CLI Reference](docs/CLI.md)
- [LLM Usage Guide](docs/LLM_USAGE.md)
- [Security Measures](docs/SECURITY_MEASURES.md)
- [Evaluation Harness](docs/EVALUATION.md)
- [Research Report](docs/RESEARCH_REPORT.md)
- [Development Status](docs/DEVELOPMENT_STATUS.md)
- [File Guide](docs/FILE_GUIDE.md)

## Contributors

- [Rohith Chikkala](https://github.com/rohith5005)
- [Praneeth Koppolu](https://github.com/iampraneethk)

## Links

- GitHub: https://github.com/rohith5005/archapi
- PyPI: https://pypi.org/project/archapi/
