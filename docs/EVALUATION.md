# Evaluation Harness

`evaluation/` is a reproducible evaluation subsystem, deliberately kept outside `archapi/` (the runtime library) — it is research/evaluation tooling, not something the library depends on.

```text
evaluation/
├── README.md
├── metrics.py    # EvaluationResult schema + pure, deterministic metric functions
├── cases.py      # EvaluationCase definitions (framework, request, fixture builder)
├── runner.py     # run_case() / run_comparison()
└── results/      # preserved historical experiment results (checked in)
```

## Two independent axes

**Context mode** — what `PromptBuilder` receives:

- `baseline` — no `retrieved_context` at all. Isolates exactly the architecture-aware-retrieval variable introduced in Phase 7.
- `archapi_retrieval` — the real production path: `RepositoryIndex` → `ContextRetriever` → `PromptBuilder`.

**Provider mode** — where the LLM response comes from:

- `deterministic` (default) — an in-memory fake provider. No network call, no cost. **This is the only mode any unit test uses.**
- `real_llm` — a real, billed OpenAI API call. Requires `confirm_real_call=True` passed explicitly to `run_case`/`run_comparison` (a code-level opt-in that raises immediately, before any network attempt, if omitted) *and* `OPENAI_API_KEY` set in the environment.

Running `python -m unittest` (any invocation) never triggers a real API call: `provider_mode` defaults to `"deterministic"`, and nothing in the test suite passes `confirm_real_call=True`.

## Running deterministic evaluation (free, no network)

```python
from evaluation.cases import get_case, CASES
from evaluation.runner import run_case, run_comparison

# Single run:
result = run_case(get_case("django_invoice"), context_mode="archapi_retrieval")

# A/B comparison -- same case (same request/framework/fixture), only the
# context strategy differs:
baseline, retrieval = run_comparison(get_case("fastapi_shipment_status"))
```

Or via the deterministic evaluation matrix already covered by `tests/test_cross_framework_evaluation.py`: a 5-framework × 4-resource grid (Express TS, FastAPI, Flask, Django REST Framework, NestJS × invoice/shipment/appointment/warranty_claim), each framework using its own idiomatic layout, proving framework detection → layer classification → resource extraction → relevance ranking → retrieval selection → prompt inclusion generalizes rather than being tuned to one fixture.

## Running real-provider evaluation (explicit opt-in, costs money)

```python
result = run_case(
    get_case("express_warranty_claim"),
    context_mode="archapi_retrieval",
    provider_mode="real_llm",
    confirm_real_call=True,   # required -- omitting it raises immediately
)
# also requires OPENAI_API_KEY set in the environment
```

The standalone script that produced the preserved historical result (`evaluation/results/phase7g_openai_6call.json`) is `scripts/phase7g_real_provider_evaluation.py` — it lives outside `tests/` and is not named `test_*.py`, so `python -m unittest` (including `discover`) can never pick it up and accidentally spend credits. It supports `--dry-run` (a fake provider, zero cost) to validate the full pipeline before making any real calls, and prompts for explicit confirmation before spending money.

```bash
# Validate plumbing, zero cost:
python scripts/phase7g_real_provider_evaluation.py --dry-run

# The real thing (asks for confirmation first):
export OPENAI_API_KEY="sk-..."
python scripts/phase7g_real_provider_evaluation.py
```

## `EvaluationResult`

Every field is an objective, measurable signal — not a subjective quality judgment:

```text
case_id, framework, request, mode, provider, model,
detected_resource,
retrieved_paths, generated_paths,
parse_success, generation_allowed, policy_gate_pass, framework_validation_pass,
architecture_score,
auth_pattern_reused, validation_pattern_reused,
expected_layers, generated_layers,
unnecessary_file_count,
errors, warnings
```

No field holds raw prompt text, repository snippet content, or a credential, so a result is always safe to serialize (`result.to_dict()`) and share. Subjective human/LLM-as-judge review, if ever added, should be a separate, clearly-labeled evaluation layer — not mixed into these deterministic metrics.

## `evaluation/results/`

`phase7g_openai_6call.json` is the preserved Phase 7G real-provider experiment (see [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md) for the interpreted findings): 3 controlled baseline-vs-`archapi_retrieval` pairs, 6 real GPT-4o-mini calls, kept byte-for-byte unmodified from the original run — including the one call that failed. It uses the original script's field names, not the `EvaluationResult` schema introduced afterward; a `schema_note` in the file documents that distinction.

Only intentionally-preserved historical experiment results are committed here. Ad-hoc/local runs written to `evaluation/results/*.local.json` or `*.scratch.json` are gitignored.
