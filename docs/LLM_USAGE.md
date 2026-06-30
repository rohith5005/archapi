# LLM Usage Guide

ArchAPI v0.4.0 introduces **LLM-first API generation** — the primary generation mode
where an LLM understands your project's architecture and generates files that match
your existing naming conventions, folder layout, validation style, service style,
and test style.

## Quick Start

```python
import os
from archapi import ArchAPI

os.environ["OPENAI_API_KEY"] = "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"   # or set in your shell

engine = ArchAPI(
    "./my_project",
    use_llm=True,
    llm_model="gpt-4o-mini",   # default
)

result = engine.generate_api(
    "Create authenticated POST API for user refund request",
    dry_run=True,
)

print("Plan    :", result.plan.method, result.plan.path)
print("Files   :", [str(f.path) for f in result.files])
print("Diff    :", result.diff)
```

## Applying Generated Files

```python
result = engine.generate_api(
    "Create authenticated POST API for user refund request",
    dry_run=False,   # writes files to disk
)
```

ArchAPI will **refuse to overwrite** existing files — it will raise `FileExistsError`
rather than silently clobbering your work.

## API Key Resolution

The OpenAI API key is resolved in this order:

1. `api_key=` constructor argument
2. `OPENAI_API_KEY` environment variable

```python
engine = ArchAPI(
    "./my_project",
    use_llm=True,
    api_key="sk-...",  # explicit, useful in CI
)
```

## Model Selection

The default model is `gpt-4o-mini` (fast, cheap, sufficient for structured JSON generation).
Switch to a more capable model for complex projects:

```python
engine = ArchAPI(
    "./my_project",
    use_llm=True,
    llm_model="gpt-4o",
)
```

## Installation

The `openai` package is an **optional dependency**:

```bash
pip install archapi[openai]
```

If you omit `[openai]`, ArchAPI will still work in deterministic mode
(`use_llm=False`, which is the default).

## Supported Frameworks (v0.4.0)

| Framework | LLM mode | Deterministic mode |
|---|---|---|
| Express TypeScript | ✅ | ✅ |
| FastAPI | ✅ | ✅ |
| Flask | ✅ | ✅ |
| NestJS | ✅ | ✅ |
| Django REST Framework | ✅ | ✅ |

## Custom LLM Provider

You can pass your own provider (e.g. Anthropic, Gemini, local Ollama) by
implementing `archapi.llm.LLMProvider` and passing it in:

```python
from archapi.llm import LLMProvider

class MyProvider(LLMProvider):
    @property
    def model_name(self) -> str:
        return "my-local-model"

    def complete(self, prompt: str) -> str:
        # call your model here
        return raw_json_string

engine = ArchAPI(
    "./my_project",
    use_llm=True,
    llm_provider=MyProvider(),
)
```

## How the Prompt is Built

ArchAPI sends the LLM:

1. **Framework + genome** — detected route/service/schema/test styles
2. **Real code snippets** — the most relevant existing files from your project
3. **Your request** — the natural language description of the API to generate
4. **JSON output schema** — strict instruction to respond with structured JSON only

The LLM response is then parsed, validated through the policy gate, secret-scanned,
and architecture-scored before being returned to you.

## Fallback: Deterministic Mode

If you prefer the original rule-based generation:

```python
engine = ArchAPI("./my_project")   # use_llm defaults to False
result = engine.generate_api("Create GET API for user orders", dry_run=True)
```

The deterministic path remains unchanged and does not require `openai`.
