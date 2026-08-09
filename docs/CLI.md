# CLI Reference

This documents the actual `archapi` command surface (verified against `archapi --help` and each subcommand's `--help`). If this ever drifts from reality, `--help` output is authoritative.

## Commands

```text
usage: archapi [-h] [--debug] <command> ...

  detect    Detect the framework of a project
  scan      Scan project structure
  plan      Plan an API without generating code (read-only)
  generate  Generate API code (dry-run by default)

  -h, --help  show this help message and exit
  --debug     Show full tracebacks on unexpected errors (default: concise
              error messages)
```

`--debug` is a top-level flag (goes before the subcommand): `archapi --debug generate ...`.

### `detect`

```text
usage: archapi detect [-h] [--json] [path]
```

Detects the framework of a project. Read-only.

```bash
archapi detect ./my-project
archapi detect ./my-project --json
```

### `scan`

```text
usage: archapi scan [-h] [--json] [path]
```

Scans the project and reports how many files were classified into each architectural layer (routes, controllers, services, models, schemas, middleware, tests, config files). Read-only.

```bash
archapi scan ./my-project
```

### `plan`

```text
usage: archapi plan [-h] [--json] [path] request
```

Infers method/path/entities/layers from a natural-language request without generating any code. Read-only.

```bash
archapi plan ./my-project "Create authenticated POST API for warranty claim"
```

### `generate`

```text
usage: archapi generate [-h] [--llm] [--model MODEL] [--apply] [--json]
                        [path] request

  --llm          Use architecture-aware LLM generation (default: deterministic)
  --model MODEL  Override the LLM model (implies nothing about --llm)
  --apply        Write files to disk (default: dry-run preview)
  --json         Machine-readable JSON output
```

`generate` is a **dry-run preview by default**. Nothing is written to disk unless `--apply` is passed explicitly.

```bash
# Deterministic, template-based generation, dry-run preview
archapi generate ./my-project "Create GET API for invoice"

# Architecture-aware LLM generation (retrieval-aware prompting), dry-run preview
archapi generate ./my-project "Create authenticated POST API for warranty claim" --llm

# Same, with an explicit model override
archapi generate ./my-project "Create PATCH API for shipment status" --llm --model gpt-4o

# Explicit filesystem mutation -- always opt-in
archapi generate ./my-project "Create authenticated POST API for warranty claim" --llm --apply
```

`use_llm` defaults to off everywhere: the CLI, the config file, and the environment variable all default to deterministic generation. `--llm` (or `use_llm = true` in `archapi.toml`, or `ARCHAPI_USE_LLM=true`) is required to opt in.

## `--json`

Every command accepts `--json` for machine-readable output (CI/tooling). JSON output contains structured results only: paths, booleans, scores, error/warning strings. It never contains raw LLM prompt text, generated file *content* (paths only), or credentials.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generation/validation rejected (PolicyGate, framework validation, or an LLM response that failed to parse) |
| `2` | Invalid CLI usage or invalid/unsafe configuration |
| `3` | LLM provider failure (missing/invalid credentials, network/API error) |

A blocked or rejected generation never produces a Python traceback in normal use. Pass `--debug` (before the subcommand) for a full traceback on unexpected errors; without it, error messages are concise and never include credentials.

There is no flag to bypass PolicyGate, framework validation, or the dry-run default. No `--skip-safety` / `--disable-policy-gate` / `--force-unsafe` option exists.

See [`CONFIGURATION.md`](CONFIGURATION.md) for how `archapi.toml` and environment variables interact with these flags.
