# Configuration

ArchAPI resolves settings with this precedence, highest to lowest:

```text
explicit Python/CLI option
        >
project config file (archapi.toml)
        >
environment variable
        >
built-in default
```

Implemented in `archapi/config.py` (`ArchAPIConfig`, `load_config`).

## `archapi.toml`

Optional, project-local. All fields are optional; anything not set falls through to the environment variable or the default.

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
controllers = 2
services = 2
schemas = 2
models = 1
tests = 2
auth_patterns = 1
validation_patterns = 1
```

**API keys never belong in `archapi.toml`, or in any config source.** ArchAPI refuses to *load* a config file (or an explicit override) whose keys look like they could hold a credential — anything containing `key`, `secret`, `token`, `password`, or `credential` — and raises a clear configuration error rather than silently accepting it. Credentials belong only in the provider's own credential mechanism: for the OpenAI provider, the `OPENAI_API_KEY` environment variable.

```toml
# This is refused at load time, not silently ignored:
[archapi.llm]
api_key = "sk-..."   # ArchAPIConfigError: looks like a credential
```

## Environment variables

| Variable | Field | Type |
|---|---|---|
| `ARCHAPI_USE_LLM` | `use_llm` | bool (`true`/`false`/`1`/`0`/`yes`/`no`/`on`/`off`) |
| `ARCHAPI_LLM_PROVIDER` | `llm_provider` | string (currently only `"openai"`) |
| `ARCHAPI_LLM_MODEL` | `llm_model` | string |
| `ARCHAPI_CONTEXT_MAX_CHARS` | `context_max_chars` | int |
| `ARCHAPI_ROUTES_LIMIT` | `routes_limit` | int |
| `ARCHAPI_CONTROLLERS_LIMIT` | `controllers_limit` | int |
| `ARCHAPI_SERVICES_LIMIT` | `services_limit` | int |
| `ARCHAPI_SCHEMAS_LIMIT` | `schemas_limit` | int |
| `ARCHAPI_MODELS_LIMIT` | `models_limit` | int |
| `ARCHAPI_TESTS_LIMIT` | `tests_limit` | int |
| `ARCHAPI_AUTH_PATTERNS_LIMIT` | `auth_patterns_limit` | int |
| `ARCHAPI_VALIDATION_PATTERNS_LIMIT` | `validation_patterns_limit` | int |
| `ARCHAPI_STRICT_VALIDATION` | `strict_validation` | bool |

`OPENAI_API_KEY` is read directly by the OpenAI provider, not by `ArchAPIConfig` — it is never one of these mapped fields, never appears in `ArchAPIConfig.to_dict()`, and is never written to a result or log.

## Fields

| Field | Default | Meaning |
|---|---|---|
| `use_llm` | `False` | Deterministic (template-based) generation vs. architecture-aware LLM generation |
| `llm_provider` | `"openai"` | Which LLM provider to construct. Unknown values fail immediately with a clear error. |
| `llm_model` | `"gpt-4o-mini"` | Model name passed to the provider |
| `context_max_chars` | `12000` | Global character budget for retrieved context sent to the LLM (Phase 7D `ContextBudget.global_char_budget`) |
| `routes_limit` / `controllers_limit` / `services_limit` / `schemas_limit` / `models_limit` / `tests_limit` | `2` / `2` / `2` / `2` / `1` / `2` | Per-category cap on how many retrieved examples of each architectural layer are included in the prompt |
| `auth_patterns_limit` / `validation_patterns_limit` | `1` / `1` | Cap on retrieved authentication/validation pattern examples |
| `strict_validation` | `False` | See below |

### `strict_validation`

Off by default, which preserves the same behavior ArchAPI has always had. When enabled, non-fatal validation *warnings* (for example, the Phase 8A naming-consistency warning — a generated file that doesn't share a naming token with any existing file of the same layer) are escalated into blocking errors.

This is strictly additive caution, never a way to loosen safety: `strict_validation` has no effect on PolicyGate or on framework-validation *errors*, which always block generation regardless of this setting. There is no configuration option, CLI flag, or environment variable that disables PolicyGate, framework validation, or the dry-run default.

## Retrieval budget

The `*_limit` and `context_max_chars` fields map directly onto the `ContextBudget` that `ContextRetriever` (Phase 7D) uses to bound how much repository context is sent to the LLM per generation call — see [`ARCHITECTURE.md`](ARCHITECTURE.md#context-retrieval--budgeting) for what each category means and [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md) for why a fixed budget matters (a naive "send the N globally highest-scoring files" strategy can starve entire architectural layers; the per-category limits guarantee representation).

## Precedence example

```bash
# 1. Environment sets a default for the whole shell session
export ARCHAPI_LLM_MODEL=gpt-4o-mini

# 2. Project config overrides it for this project only
cat > archapi.toml <<'EOF'
[archapi.llm]
model = "gpt-4o"
EOF

# 3. An explicit CLI override wins over both
archapi generate . "Create GET API for invoice" --llm --model gpt-4o-mini
```

In this example the actual model used is `gpt-4o-mini` — the explicit `--model` flag, even though both the environment variable and `archapi.toml` also set a value.
