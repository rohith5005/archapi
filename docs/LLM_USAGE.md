# LLM Usage Guide

ArchAPI's LLM-assisted generation mode (`--llm` / `use_llm=True`) uses an architecture-aware retrieval pipeline (Phase 7) to select the repository examples most relevant to your request, then asks the LLM to imitate those patterns — naming, structure, imports, error handling, existing auth/validation mechanisms — rather than generating from a generic prompt or arbitrary repository files.

Deterministic generation (`use_llm=False`, the default everywhere — CLI, config, and Python API) never requires the `openai` package and works fully offline.

## Quick start (CLI)

```bash
export OPENAI_API_KEY="sk-..."

archapi generate ./my-project \
  "Create authenticated POST API for warranty claim" \
  --llm
```

Dry-run by default — nothing is written until you add `--apply`:

```bash
archapi generate ./my-project \
  "Create authenticated POST API for warranty claim" \
  --llm --apply
```

## Quick start (Python)

```python
from archapi import ArchAPI

engine = ArchAPI(
    "./my-project",
    use_llm=True,
    llm_model="gpt-4o-mini",   # default
)

result = engine.generate_api(
    "Create authenticated POST API for warranty claim",
    dry_run=True,
)

print("Plan   :", result.plan.method, result.plan.path)
print("Files  :", [str(f.path) for f in result.files])
print("Diff   :", result.diff)
```

To see exactly what was retrieved for this generation:

```python
context = engine._last_retrieved_context
for item in context.all_items():
    print(item.layer, item.path, item.score, item.reasons)
```

## What retrieval actually selects

For a request like `"Create PATCH API for shipment status"` against a project that also has invoice- and appointment-related code, retrieval:

1. Indexes the repository's source files (`archapi/indexing/repository_index.py`) — symbols, imports, HTTP methods, route paths, entity terms, auth/validation indicators.
2. Scores every indexed file against the inferred resource (`shipment`), method (`PATCH`), and whether the request mentions authentication/validation (`archapi/indexing/relevance_scorer.py`) — deterministic lexical/structural signals, not embeddings.
3. Selects a budgeted, per-category set of the highest-scoring examples (`archapi/indexing/context_retriever.py`) — a few relevant routes, one or two services/schemas, an auth example only if authentication was requested, a validation example only if validation was requested, one or two tests — so unrelated invoice/appointment code is not sent, and no single category (or the whole prompt) can grow unbounded.

The resulting prompt (`archapi/llm/prompt_builder.py`) makes this explicit to the model, in labeled sections:

```text
## PROJECT ARCHITECTURE
...
## USER REQUEST
...
## IMPLEMENTATION PLAN
...
## RELEVANT EXISTING PROJECT EXAMPLES

[ROUTE] app/routers/shipment_router.py
```
...
```

[SERVICE] app/services/shipment_service.py
```
...
```

[VALIDATION PATTERN] app/schemas/shipment_schema.py
```
...
```
...
## GENERATION RULES
```

Retrieved content is redacted for secret-shaped values immediately before the request is sent (`archapi/security/context_redactor.py`) — see [`SECURITY_MEASURES.md`](SECURITY_MEASURES.md). Score/reason data stays server-side for research instrumentation and is not sent to the model.

Full pipeline diagram: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Applying generated files

```python
result = engine.generate_api(
    "Create authenticated POST API for warranty claim",
    dry_run=False,   # writes files to disk
)
```

Only if `result.validation_report.success` — PolicyGate and framework validation must both pass. ArchAPI refuses to overwrite an existing file for a `"create"`-action file (raises `FileExistsError`) rather than silently clobbering it, and if a multi-file write fails partway through, everything already written in that attempt is rolled back (`archapi/generation/file_transaction.py`) — see [`SECURITY_MEASURES.md`](SECURITY_MEASURES.md).

## API key resolution

The OpenAI API key is resolved in this order:

1. `api_key=` constructor argument
2. `OPENAI_API_KEY` environment variable

```python
engine = ArchAPI(
    "./my-project",
    use_llm=True,
    api_key="sk-...",  # explicit, useful in CI
)
```

It is never read from `archapi.toml` or any other config source — see [`CONFIGURATION.md`](CONFIGURATION.md).

## Model selection

```bash
archapi generate ./my-project "Create GET API for invoice" --llm --model gpt-4o
```

```python
engine = ArchAPI("./my-project", use_llm=True, llm_model="gpt-4o")
```

Or via `archapi.toml` / `ARCHAPI_LLM_MODEL` — see [`CONFIGURATION.md`](CONFIGURATION.md) for precedence.

## Installation

The `openai` package is an optional dependency:

```bash
pip install "archapi[openai]"
```

Without it, ArchAPI still works fully in deterministic mode (`use_llm=False`, the default).

## Supported frameworks

Dedicated adapters — retrieval, layer classification, and framework validation all have framework-specific behavior:

| Framework | LLM-assisted | Deterministic |
|---|---|---|
| Express TypeScript | yes | yes |
| FastAPI | yes | yes |
| Flask | yes | yes |
| Django REST Framework | yes | yes |
| NestJS | yes | yes |

Anything else falls back to a generic, lower-confidence adapter (deterministic path only recommends `plan_only`/`blocked` modes at low confidence; see `ArchAPI.compute_confidence()`).

## Custom LLM provider

```python
from archapi.llm import LLMProvider

class MyProvider(LLMProvider):
    @property
    def model_name(self) -> str:
        return "my-local-model"

    def complete(self, prompt: str) -> str:
        # call your model here; must return the raw response text
        return raw_json_string

engine = ArchAPI(
    "./my-project",
    use_llm=True,
    llm_provider=MyProvider(),
)
```

The retrieval pipeline, prompt structure, redaction, and safety gates are identical regardless of which provider produces the completion.

## Fallback: deterministic mode

```python
engine = ArchAPI("./my-project")   # use_llm defaults to False everywhere
result = engine.generate_api("Create GET API for invoice", dry_run=True)
```

The deterministic path generates from fixed per-framework templates and does not use retrieval, `PromptBuilder`, or `openai` at all — it goes straight from the inferred plan to code generation, then through the same PolicyGate/framework-validation/architecture-score/`FileTransaction` stages as the LLM path.
