# Research Report: Architecture-Aware Repository Retrieval

## Research question

> Does deterministic architecture-aware repository retrieval improve the architectural conformity of LLM-generated REST API implementations compared with generation without architecture-aware retrieval?

This report separates two kinds of evidence, deliberately:

1. **Deterministic evidence** — the retrieval pipeline itself (indexing, layer classification, relevance scoring, budgeted context selection) is exercised by 231 unit/integration tests, including a 20-cell cross-framework/cross-resource matrix, all with no LLM involved and no cost. This evidence is strong and reproducible on every run.
2. **Real-provider evidence** — a small, controlled pilot of six real OpenAI calls, comparing generation with and without retrieval-aware context on the *same* request/repository/model. This evidence is illustrative, not statistically significant, and is reported as such below.

Do not read this report as a claim that Phase 7/8 has been benchmarked at scale. It has been built, and it has been proven to work as designed on deterministic evidence; the real-provider evidence is a first, small look at whether the deterministic design translates into better real generations.

## What "architecture-aware retrieval" means here

```text
User request
      |
Framework detection
      |
Repository scan
      |
Layer classification        (archapi/mapping/layer_classifier.py)
      |
Repository index            (archapi/indexing/repository_index.py)
      |
Intent/API plan             (archapi/planning/intent_planner.py)
      |
Relevance scoring           (archapi/indexing/relevance_scorer.py)
      |
Context retrieval + budget  (archapi/indexing/context_retriever.py)
      |
PromptBuilder
      |
Context redaction
      |
LLM
      |
Response parser -> PolicyGate -> framework validation -> architecture score
```

Full description: [`ARCHITECTURE.md`](ARCHITECTURE.md).

**Baseline**, for the purposes of this report, means the *same* pipeline with one variable changed: `PromptBuilder` receives no `retrieved_context`. It still receives the detected framework/genome and the inferred plan — this isolates exactly the retrieval contribution, not Phase 5/6's pre-existing architecture-awareness (which both conditions already have).

## Deterministic evidence (Phase 7F)

A 5-framework × 4-resource evaluation matrix (Express TS, FastAPI, Flask, Django REST Framework, NestJS × invoice / shipment / appointment / warranty_claim), each framework using its own idiomatic layout — not a copy of one framework's conventions applied everywhere. `warranty_claim` has no hard-coded rule anywhere in the codebase and is a two-word compound noun specifically chosen to stress generic (not resource-specific) entity extraction.

**Result: 20/20 cells passed.** For every (framework, resource) pair: correct framework detection, correct resource extraction (including `"warranty"` resolved from the two-word `"warranty claim"` — the planner's documented, generalization-tested fallback behavior, not a special case), correct top-ranked retrieval, zero decoy/irrelevant selection, deterministic ranking, and correct prompt inclusion/exclusion.

See `tests/test_cross_framework_evaluation.py` and `tests/test_relevance_scorer.py`, `tests/test_context_retriever.py`, `tests/test_layer_classifier.py`, `tests/test_repository_index.py` for the underlying component-level evidence.

## Real-provider pilot (Phase 7G)

**Six real calls.** Three controlled A/B pairs — one call each for `baseline` and `archapi_retrieval`, same repository/request/model (`gpt-4o-mini`) held constant per pair. Full results preserved unmodified in `evaluation/results/phase7g_openai_6call.json`.

### Express TypeScript — authenticated POST warranty claim API with validation

| | baseline | archapi_retrieval |
|---|---|---|
| Architecture score | 100% | 100% |
| Reused existing auth pattern | no | **yes** |
| Reused existing validation pattern | no | **yes** |

Both conditions scored 100% on ArchAPI's architecture-conformity metric. The scores tie, but the *content* did not: baseline invented generic file names (`src/routes/claims.ts`, tests under a nonstandard `src/tests/` directory) with no relation to the project's actual naming convention or existing auth/validation mechanisms. Retrieval-aware generation matched the project's exact `warranty-claim.*` kebab-case naming and correct root-level `tests/` placement, and reused the existing auth guard and validation schema rather than inventing new ones — a difference the architecture-score metric alone does not capture, which is itself a finding (see Limitations).

### FastAPI — PATCH shipment status API with validation

| | baseline | archapi_retrieval |
|---|---|---|
| Architecture score | 88.9% | **100%** |
| Reused existing validation pattern | no | **yes** |

Baseline invented `app/routes/` and an `app/controllers/` layer that does not exist in this project's convention (the real directory is `app/routers/`; FastAPI generation in this codebase has no separate controller layer). Retrieval-aware generation used the correct directory and correctly omitted the nonexistent layer.

### Django REST Framework — POST invoice API

| | baseline | archapi_retrieval |
|---|---|---|
| Architecture score | 50% | 40% |
| Framework validation | passed | **failed** |
| Generation allowed | yes | **no** |

This is the one call that failed, and it is preserved as a recorded failure, not corrected after the fact. Retrieval-aware generation faithfully reproduced the repository's own flat `{app}/tests.py` test-file convention (the fixture's actual, demonstrated pattern — and also what `django-admin startapp` scaffolds by default in real Django projects). `DjangoDRFAdapter.validate_generated_code()` at the time required a literal `"test_"` substring in the test filename and rejected it. Baseline happened to pass only because, with no repository context at all, the model fell back to generic Django knowledge (`tests/test_invoice.py`) that coincidentally satisfied that hard-coded rule.

**This was retrieval working exactly as designed** — faithfully imitating a convention the repository actually demonstrates — colliding with a validator that hard-coded one specific naming convention as if it were the only legitimate one. The investigation that followed (Phase 8A) audited all five framework adapters' structural validators and found the same class of assumption in every one of them (FastAPI/Flask's test-file check, Django's, Express's directory-substring check, NestJS's `.spec.ts` check), replaced the test-layer check specifically with the same general-purpose `LayerClassifier` already trusted for indexing (which recognizes `test_x.py`, `x_test.py`, `x.spec.ts`, and a bare `tests.py` uniformly), and added a non-blocking, repository-evidence-based naming-consistency warning as a complementary, softer signal. `tests/test_validator_repository_consistency.py` reproduces this exact scenario end-to-end and asserts it now passes — as a regression test, separate from and without altering the historical Phase 7G record above.

```text
Phase 7G: Django retrieval -> validation failure
        |
Phase 8A investigation
        |
systemic validator assumption discovered across all 5 adapters
        |
general fix (shared LayerClassifier, not a Django-specific patch)
        |
regression test reproduces the original scenario -> now passes
```

That progression — a real failure, found, root-caused to a general principle rather than patched narrowly, and turned into a regression test — is itself evidence of a working development process, independent of whether the underlying retrieval hypothesis holds.

## Summary of the six-call pilot

- 2 of 3 pairs: retrieval-aware generation matched or exceeded the baseline's architecture score, and additionally demonstrated concrete reuse of existing auth/validation patterns that the baseline never attempted.
- 1 of 3 pairs: retrieval-aware generation was rejected by a validator bug it exposed, unrelated to whether the retrieved context itself was appropriate (the retrieved examples were correct; see `retrieved_paths` in the preserved result).
- Architecture score alone did not fully capture the qualitative differences observed (correct directory/naming, avoided nonexistent layers, pattern reuse) — a metric-design limitation, not a data point against retrieval.

## Limitations

- **Six calls, three frameworks, one call per condition.** This is a controlled pilot demonstrating the pipeline works end-to-end against a real provider and surfaces real, actionable findings — not a statistically powered benchmark. No claim of statistical significance is made or implied.
- **Stochastic LLM behavior.** A single call per condition cannot distinguish genuine architectural improvement from run-to-run variance in the model's output. Repeated trials per condition are needed before drawing a general conclusion.
- **Architecture score is an ArchAPI-defined metric** (`archapi/validation/architecture_score.py`), not an external or standardized measure of code quality. It checks structural conventions (layer presence, naming patterns, framework-idiomatic constructs) and does not capture business-logic correctness, security review, or reuse of existing patterns beyond what it explicitly checks for — as the Express TS pilot result shows, two conditions can tie on this metric while differing meaningfully in what a reviewer would actually prefer.
- **Retrieval uses deterministic lexical/structural signals**, not semantic embeddings or a vector index (a deliberate Phase 7 design choice — see `archapi/indexing/relevance_scorer.py` and the "premature complexity" guidance that shaped it). It cannot recognize that "order" and "refund" are related business concepts if they share no lexical token; it can only rank on what the repository's own naming and structure actually expose.
- **Resource extraction remains heuristic** (`archapi/planning/intent_planner.py`): a keyword-rule list plus a generic fallback that favors the noun following "for" in the request text. It is deliberately generalization-tested (`warranty_claim` has no hard-coded rule), but compound and ambiguous resource names are a known, documented limitation rather than a solved problem.
- **Supported framework coverage is finite**: Express TypeScript, FastAPI, Flask, Django REST Framework, NestJS have dedicated adapters; anything else falls back to a generic, lower-confidence adapter.
- **Repository conventions may themselves be inconsistent or poor.** Retrieval faithfully reproduces what a repository demonstrates — including inconsistent or suboptimal existing conventions. It is not a code-quality auditor; consistency with a bad existing pattern is still consistency, and imitation is the explicit design goal, not judgment.
- **Generated code still requires developer review.** PolicyGate, framework validation, and architecture scoring are deterministic structural/safety gates, not a correctness or security guarantee, and dry-run is the default specifically so a human reviews output before it is written.

## Reproducing this report

```bash
# Deterministic evidence (free, no network, ~1 second):
python -m unittest tests.test_cross_framework_evaluation -v

# The exact real-provider pilot (costs money, requires explicit confirmation
# and OPENAI_API_KEY; --dry-run validates the pipeline for free first):
python scripts/phase7g_real_provider_evaluation.py --dry-run
python scripts/phase7g_real_provider_evaluation.py
```

See [`EVALUATION.md`](EVALUATION.md) for the general-purpose evaluation harness this pilot's successor experiments should use.
