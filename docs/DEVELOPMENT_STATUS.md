# Development Status

## Phase 1 — Core foundation

Complete.

Library foundation, core `ArchAPI` class, Express adapter, generic fallback adapter, scan/map/genome/confidence, dry-run generation, safe apply, overwrite protection, cache, baseline security.

## Phase 2 — Improved planning and Express support

Complete.

Improved REST planning, architecture score, command validation, strict config mode, improved Express generation.

## Phase 3 — Multi-framework support

Complete.

FastAPI adapter, FastAPI sample project, cross-framework behavior, unified test suite. Flask, Django REST Framework, and NestJS adapters followed, bringing dedicated support to five frameworks.

## Phase 4 — Packaging, docs, release

Complete.

Packaging for PyPI, initial documentation set, 0.5.0 release line.

## Phase 5 — Real LLM integration

Complete.

`OpenAIProvider`, `PromptBuilder`, `ResponseParser`; LLM-assisted generation path (`use_llm=True`) alongside the deterministic path.

## Phase 6 — LLM safety

Complete.

`PolicyGate` (absolute-path/traversal rejection, project-root containment, protected files/directories, bootstrap/config-file controls, unrequested-middleware rejection, generated-secret detection), `ContextRedactor`, `SecretScanner`, framework-adapter validation of LLM output, architecture consistency scoring, `dry_run` protection, adversarial safety tests. See [`SECURITY_MEASURES.md`](SECURITY_MEASURES.md).

## Phase 7 — Architecture-aware repository retrieval

Complete.

Replaced arbitrary/first-found repository context (`routes[0]`, `services[0]`, ...) with a deterministic, request-aware retrieval pipeline:

- **7A** Repository index (`archapi/indexing/repository_index.py`)
- **7B** Repository-relative layer classification (`archapi/mapping/layer_classifier.py`) — fixed a real bug where a project root directory name embedding a layer keyword (e.g. `identity-service` containing "service") distorted classification of every file inside it
- **7C** Deterministic relevance scoring (`archapi/indexing/relevance_scorer.py`)
- **7D** Context retriever + budget (`archapi/indexing/context_retriever.py`)
- **7E** Prompt/LLM integration — `PromptBuilder` now consumes retrieved context; arbitrary selection removed
- **7F** Cross-framework/resource evaluation: 20/20 on a 5-framework × 4-resource matrix, including a resource with no hard-coded rule anywhere (`warranty_claim`)
- **7G** Real-provider pilot: 6 real OpenAI calls, 3 controlled baseline-vs-retrieval pairs, preserved in `evaluation/results/phase7g_openai_6call.json`

See [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md) for the evidence and its limitations.

## Phase 8 — Production hardening + research evaluation + v1.0 preparation

| Sub-phase | Status |
|---|---|
| 8A Repository-aware validation | **COMPLETE** |
| 8B Evaluation harness | **COMPLETE** |
| 8C Configuration + CLI | **COMPLETE** |
| 8D Reliability + CI | **COMPLETE** |
| 8E Documentation | **COMPLETE** |
| 8F v1.0 release candidate | **IN PROGRESS** |
| 8G v1.0 release | PENDING |

### 8A — Repository-aware validation

Audited all five framework adapters' structural validators for hardcoded naming assumptions that could reject a legitimate, repository-observed convention (the Phase 7G Django finding). Every adapter's test-layer check now uses the shared `LayerClassifier` instead of one hardcoded pattern; a non-blocking, evidence-based naming-consistency warning was added. `tests/test_validator_repository_consistency.py`.

### 8B — Reproducible evaluation harness

`evaluation/` (`cases.py`, `metrics.py`, `runner.py`, `results/`): deterministic and real-provider evaluation modes, baseline-vs-`archapi_retrieval` comparison, an objective-signals-only `EvaluationResult` schema, the Phase 7G result preserved unmodified. See [`EVALUATION.md`](EVALUATION.md).

### 8C — Production configuration + CLI

`archapi/config.py` (`ArchAPIConfig`, precedence: CLI flag > `archapi.toml` > environment variable > default) and a completed `archapi/cli.py`: `--llm` (previously unreachable from the CLI), `--model`, `--json`, `--apply`-gated writes, documented exit codes, no credential ever printed or logged. See [`CONFIGURATION.md`](CONFIGURATION.md) and [`CLI.md`](CLI.md).

### 8D — Reliability + CI

`archapi/generation/file_transaction.py`: atomic multi-file application with rollback on partial failure, no git dependency. Clean-install verification (fresh venv, wheel-only install). `.github/workflows/test.yml`: matrix CI across the Python versions this project declares support for, plus a targeted secret scan. `tests/test_reliability.py`.

### 8E — Documentation

Brought `README.md` and `docs/` up to date with the system as it actually exists: architecture, configuration, CLI, security boundary, evaluation harness, and a research report that reports the Phase 7G pilot's real result — including the one call that failed — rather than a retroactively corrected one.

### 8F — v1.0 release candidate (this phase)

Version moved to `1.0.0`. Full deterministic gate, secret audit, exact release artifacts built and inspected (wheel contains only `archapi/*` runtime files — no `evaluation/`, `tests/`, or scratch content), clean-wheel installation into an isolated venv verified from outside the repo checkout, installed-CLI smoke tests (scan/plan/generate, `--json`, `archapi.toml` including a deliberately invalid config failing safely, atomic `--apply`), and one controlled real-LLM dry-run against the installed wheel with a freshly-provided credential (a previously-used key was treated as no longer trustworthy for this step and not reused).

### 8G — Not started

Tag `v1.0.0`, publish the already-verified artifacts to PyPI, create the GitHub release, verify installation from PyPI in another clean environment, announce.

## Test count

`python -m unittest discover -s tests -v` — 231 tests passing as of Phase 8D, zero real network calls. The exact count grows as phases add coverage; treat it as a floor, not a fixed target.
