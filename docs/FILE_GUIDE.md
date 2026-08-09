# File Guide

## Root files

- `README.md`: project overview and quickstart
- `pyproject.toml`: Python package metadata
- `.gitignore`: local/generated file exclusions
- `.github/workflows/test.yml`: CI (test matrix + secret scan)

## Main package (`archapi/`)

- `archapi/__init__.py`: public package export (`ArchAPI`, `__version__`)
- `archapi/core.py`: main orchestration class (`ArchAPI`)
- `archapi/types.py`: shared dataclasses (`ScanResult`, `APIGenome`, `APIPlan`, `GeneratedFile`, `ValidationReport`, `GenerationResult`)
- `archapi/config.py`: central configuration (`ArchAPIConfig`, `load_config`) — see [Configuration](CONFIGURATION.md)
- `archapi/cli.py`: the `archapi` console command — see [CLI Reference](CLI.md)

## Frameworks (`archapi/frameworks/`)

- `archapi/frameworks/base.py`: adapter interface (`FrameworkAdapter`)
- `archapi/frameworks/detector.py`: framework detection
- `archapi/frameworks/registry.py`: adapter registry
- `archapi/frameworks/generic.py`: fallback adapter + shared adapter helpers (scan, `LayerClassifier`-based structural validation, naming-consistency warnings)
- `archapi/frameworks/express_ts/adapter.py`: Express TypeScript adapter
- `archapi/frameworks/fastapi_adapter.py`: FastAPI adapter
- `archapi/frameworks/flask_adapter.py`: Flask adapter
- `archapi/frameworks/django_drf_adapter.py`: Django REST Framework adapter
- `archapi/frameworks/nestjs/adapter.py`: NestJS adapter

## Mapping (`archapi/mapping/`)

- `archapi/mapping/layer_classifier.py`: `LayerClassifier` — the single, token-based classification authority used by both scanning and validation

## Indexing / retrieval (`archapi/indexing/`)

- `archapi/indexing/cache.py`: cache and changed-file detection
- `archapi/indexing/repository_index.py`: `RepositoryIndex`/`IndexedUnit` — deterministic local indexing of source-code units
- `archapi/indexing/relevance_scorer.py`: `RelevanceScorer`/`ScoredUnit` — deterministic, explainable relevance scoring
- `archapi/indexing/context_retriever.py`: `ContextRetriever`/`ContextBudget`/`RetrievedContext` — budgeted context selection

## Planning (`archapi/planning/`)

- `archapi/planning/intent_planner.py`: natural-language request → method/path/entities/layers
- `archapi/planning/task_dag.py`: task dependency model

## LLM (`archapi/llm/`)

- `archapi/llm/base.py`: `LLMProvider` interface
- `archapi/llm/openai_provider.py`: OpenAI-backed provider
- `archapi/llm/prompt_builder.py`: `PromptBuilder` — renders retrieved context into the final prompt
- `archapi/llm/response_parser.py`: parses the LLM's JSON response
- `archapi/llm/errors.py`: `LLMProviderError`, `LLMParseError`

## Generation (`archapi/generation/`)

- `archapi/generation/file_transaction.py`: `FileTransaction` — atomic multi-file application with rollback

## Security (`archapi/security/`)

- `archapi/security/secret_scanner.py`: secret scanner
- `archapi/security/context_redactor.py`: prompt redactor
- `archapi/security/policy_gate.py`: output safety gate (`PolicyGate`)

## Validation (`archapi/validation/`)

- `archapi/validation/architecture_score.py`: architecture consistency scoring
- `archapi/validation/command_validator.py`: optional command validation

## Evaluation (`evaluation/`, outside the `archapi/` runtime package)

- `evaluation/cases.py`: `EvaluationCase` definitions
- `evaluation/metrics.py`: `EvaluationResult` schema + deterministic metric functions
- `evaluation/runner.py`: `run_case()`/`run_comparison()`
- `evaluation/results/`: preserved historical experiment results — see [Evaluation](EVALUATION.md)

## Scripts (`scripts/`)

- `scripts/phase7g_real_provider_evaluation.py`: standalone real-provider evaluation script (outside `tests/`, never auto-discovered)
- `scripts/test_openai_llm.sh`: live single-project OpenAI integration smoke test
- `scripts/run_tests.sh`: convenience wrapper for the test suite

## Tests (`tests/`)

- `tests/test_archapi_suite.py`: core generation/safety regression suite
- `tests/test_layer_classifier.py`, `test_repository_index.py`, `test_relevance_scorer.py`, `test_context_retriever.py`: retrieval pipeline components
- `tests/test_prompt_retrieval_integration.py`: retrieval → prompt integration
- `tests/test_cross_framework_evaluation.py`: 5-framework × 4-resource deterministic retrieval matrix
- `tests/test_validator_repository_consistency.py`: framework-validator/repository-evidence consistency (Phase 8A)
- `tests/test_evaluation_harness.py`: evaluation harness self-tests
- `tests/test_config.py`, `test_cli.py`: configuration and CLI
- `tests/test_reliability.py`: atomic application, rollback, and failure-path tests

## Docs (`docs/`)

- `docs/HOW_TO_RUN.md`: install/run/test walkthrough
- `docs/ARCHITECTURE.md`: full pipeline description
- `docs/CONFIGURATION.md`: `archapi.toml`/environment variables
- `docs/CLI.md`: command reference
- `docs/LLM_USAGE.md`: LLM-assisted generation walkthrough
- `docs/SECURITY_MEASURES.md`: the full safety boundary
- `docs/EVALUATION.md`: the evaluation harness
- `docs/RESEARCH_REPORT.md`: what was tested and what the evidence supports
- `docs/DEVELOPMENT_STATUS.md`: phase-by-phase status
- `docs/FILE_GUIDE.md`: this file
- `docs/GITHUB_QUICKSTART.md`: minimal clone-and-run steps
