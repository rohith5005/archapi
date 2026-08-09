# ArchAPI Evaluation Harness (Phase 8B)

Turns the Phase 7F/7G experiments into a reproducible subsystem: given a
project + API request + generation mode, run ArchAPI and produce a
deterministic, machine-readable `EvaluationResult`.

This package is intentionally kept outside `archapi/` (the runtime
library) — it is research/evaluation tooling, not a component the public
library depends on.

See [`docs/EVALUATION.md`](../docs/EVALUATION.md) for the full usage guide
and [`docs/RESEARCH_REPORT.md`](../docs/RESEARCH_REPORT.md) for what the
Phase 7G pilot in `results/phase7g_openai_6call.json` actually shows and
its limitations.

## Layout

```
evaluation/
├── README.md
├── metrics.py    # EvaluationResult schema + pure, deterministic metric functions
├── cases.py      # EvaluationCase definitions (framework, request, fixture builder)
├── runner.py     # run_case() / run_comparison()
└── results/      # preserved historical experiment results (checked in)
```

## Two independent axes

**Context mode** — what PromptBuilder receives:
- `baseline` — no `retrieved_context` at all. Isolates exactly the Phase 7
  retrieval variable.
- `archapi_retrieval` — the real production path: `RepositoryIndex` →
  `ContextRetriever` → `PromptBuilder`.

**Provider mode** — where the LLM response comes from:
- `deterministic` (default) — an in-memory fake provider. No network call,
  no cost. **This is the only mode any unit test may use.**
- `real_llm` — a real, billed OpenAI API call. Requires:
  1. `confirm_real_call=True` passed explicitly to `run_case`/`run_comparison`
     (a code-level opt-in — omitting it raises immediately, before any
     network attempt), **and**
  2. `OPENAI_API_KEY` set in the environment (never read from a file this
     package touches, never accepted as a parameter here, never written to
     a result).

Running `python -m unittest` (any invocation, any discovery mode) never
triggers a real API call — `provider_mode` defaults to `"deterministic"`,
and no call site in `tests/test_evaluation_harness.py` passes
`provider_mode="real_llm"`.

## Usage

```python
from evaluation.cases import get_case, CASES
from evaluation.runner import run_case, run_comparison

# Single run, deterministic (free, no network):
result = run_case(get_case("django_invoice"), context_mode="archapi_retrieval")

# A/B comparison, same case, same model, only context strategy differs:
baseline, retrieval = run_comparison(get_case("fastapi_shipment_status"))

# Real provider (costs money -- explicit opt-in required):
result = run_case(
    get_case("express_warranty_claim"),
    context_mode="archapi_retrieval",
    provider_mode="real_llm",
    confirm_real_call=True,   # <- required
)  # also requires OPENAI_API_KEY set in the environment
```

`EvaluationResult` (see `metrics.py`) is a plain dataclass of objective,
measurable signals — framework validation pass/fail, architecture score,
expected vs. generated layer coverage, unnecessary-file count,
auth/validation-pattern reuse, policy-gate result, parse success, plus
errors/warnings. It deliberately has no field for raw prompt text,
repository snippet content, or any credential, so it is always safe to
serialize with `result.to_dict()` and share.

Subjective quality judgments (human or LLM-as-judge review) are out of
scope here by design — if added later, they should be a separate,
clearly-labeled evaluation layer, not mixed into these deterministic
metrics.

## `results/`

`results/phase7g_openai_6call.json` is the preserved, unmodified Phase 7G
real-provider experiment: 3 controlled baseline-vs-`archapi_retrieval`
pairs (Express TS, FastAPI, Django DRF), 6 real GPT-4o-mini calls. It uses
the original Phase 7G script's field names (see
`scripts/phase7g_real_provider_evaluation.py`), not the `EvaluationResult`
schema introduced afterward in this package — preserved verbatim for
historical fidelity.

The Django `archapi_retrieval` result in that file is a genuine recorded
**failure**: retrieval faithfully reproduced the repository's own flat
`tests.py` convention, and `DjangoDRFAdapter.validate_generated_code()`
rejected it for lacking a literal `"test_"` substring — a disagreement
between repository evidence and ArchAPI's own validator, not a retrieval
defect. It is intentionally left as a recorded failure rather than
rewritten to reflect the Phase 8A fix; `tests/test_validator_repository_consistency.py`
reproduces the same scenario and asserts it now passes, so the historical
record and the regression coverage stay separate and both stay honest.
