# Architecture

ArchAPI has two generation paths that share the same detection, scanning, planning, safety, and validation machinery, and diverge only in how the actual code is produced:

- **Deterministic generation** — rule-based, template-driven, works fully offline, no LLM required.
- **LLM-assisted generation** (`--llm` / `use_llm=True`) — an LLM writes the code, guided by an architecture-aware prompt built from repository evidence the retrieval pipeline selects.

## Full pipeline (LLM-assisted path)

```text
User request
      |
Framework detection            archapi/frameworks/detector.py
      |
Repository scan                archapi/frameworks/generic.py (adapter.scan)
      |
Layer classification           archapi/mapping/layer_classifier.py
      |
Repository index               archapi/indexing/repository_index.py
      |
Intent/API plan                archapi/planning/intent_planner.py
      |
Relevance scoring               archapi/indexing/relevance_scorer.py
      |
Context retrieval + budgeting  archapi/indexing/context_retriever.py
      |
PromptBuilder                  archapi/llm/prompt_builder.py
      |
Context redaction              archapi/security/context_redactor.py
      |
LLM                            archapi/llm/openai_provider.py
      |
Response parser                archapi/llm/response_parser.py
      |
PolicyGate                     archapi/security/policy_gate.py
      |
Framework validation           archapi/frameworks/*_adapter.py (validate_generated_code)
      |
Architecture score             archapi/validation/architecture_score.py
      |
GenerationResult                archapi/types.py
      |
FileTransaction                 archapi/generation/file_transaction.py
      |
Atomic application / rollback
```

The deterministic path shares everything from framework detection through planning, then generates code from fixed templates per framework/layer instead of calling an LLM, and goes through the same PolicyGate, framework validation, architecture scoring, and `FileTransaction` application as the LLM path.

## Stage by stage

### Framework detection

`archapi/frameworks/detector.py` looks for framework markers (`package.json` dependencies, `requirements.txt`/`pyproject.toml` contents, `manage.py`, etc.) and returns a `DetectionResult` with a confidence score. Dedicated adapters exist for Express TypeScript, FastAPI, Flask, Django REST Framework, and NestJS (`archapi/frameworks/registry.py`); anything else falls back to a generic, lower-confidence adapter.

### Repository scan

Each framework adapter's `scan()` walks the project and classifies every file into a `ScanResult` bucket (routes, controllers, services, models, schemas, middleware, tests, config files).

### Layer classification

`archapi/mapping/layer_classifier.py` (`LayerClassifier`) is the single classification authority behind the scan — token-based (not raw substring matching), evaluated on the path *relative to the project root* so a project directory name that happens to embed a keyword (e.g. `identity-service` containing "service") never distorts classification of files inside it. Precedence: a file's own filename and immediate parent directory are checked first (test > middleware > route > controller > service > schema > model), falling back to ancestor directories only if neither matches.

### Repository index

`archapi/indexing/repository_index.py` turns the scan into a queryable, in-memory index of source-code units: path, layer, language, symbols, imports, HTTP methods, route paths, entity terms, auth/validation indicators, test flag, and a bounded snippet — all extracted via local regex/lightweight parsing, no embeddings, no external index.

### Intent/API plan

`archapi/planning/intent_planner.py` infers method/path/entities/layers from the natural-language request. On the LLM path this plan is a *hint* used to drive retrieval and shown to the model as guidance — it does not gate generation; the LLM's own response, once parsed, becomes the actual plan. On the deterministic path the plan directly drives which templates get filled in.

### Relevance scoring

`archapi/indexing/relevance_scorer.py` scores every indexed unit against the plan using deterministic, explainable signals: resource/entity match, architectural-layer match, HTTP method match, route-path similarity, auth/validation requirement match (detected from the request text), symbol/token similarity, and test relevance. No embeddings, no LLM involved in scoring.

### Context retrieval + budgeting

`archapi/indexing/context_retriever.py` (`ContextRetriever`) turns the ranking into a bounded, structured selection: per-category top-K (so a naive "top N globally" strategy can't starve an entire layer — see [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md) for why this matters empirically), deduplicated by path, then a shared global character budget applied via a priority-ordered greedy pass that is provably monotonic (a higher-ranked item, once included, is never later removed as the budget grows). Budget is configurable — see [`CONFIGURATION.md`](CONFIGURATION.md).

### PromptBuilder

`archapi/llm/prompt_builder.py` renders the retrieved context into labeled sections (`[ROUTE]`, `[SERVICE]`, `[AUTHENTICATION PATTERN]`, `[VALIDATION PATTERN]`, `[TEST]`, ...), telling the model to imitate the patterns shown rather than copy their business logic, and to reuse existing auth/validation conventions rather than invent new ones. It does not select which files are relevant itself — that is `ContextRetriever`'s job — and if no retrieved context is supplied it produces architecture/genome/request/plan information only, never falling back to arbitrary file selection.

### Context redaction

`archapi/security/context_redactor.py` redacts secret-shaped values from the fully assembled prompt exactly once, after retrieval and prompt construction, before the provider call. Retrieval and prompt rendering both preserve original (unredacted) snippets by design, so redaction has one single, auditable point of enforcement.

### LLM

`archapi/llm/openai_provider.py` sends the redacted prompt to OpenAI and returns the raw response. The `openai` package is an optional extra (`pip install archapi[openai]`); deterministic generation never needs it.

### Response parser

`archapi/llm/response_parser.py` parses the LLM's JSON response into a plan and a list of generated files, strict about required fields and basic types, lenient about extra ones.

### PolicyGate

`archapi/security/policy_gate.py` — the output safety gate shared by both generation paths. See [`SECURITY_MEASURES.md`](SECURITY_MEASURES.md) for the full boundary.

### Framework validation

Each adapter's `validate_generated_code()` checks structural conformance (required layers present, no empty files) using the shared `LayerClassifier` for naming-convention checks that legitimately vary (e.g. test-file naming), and exact-match checks only where a framework has no realistic naming variance (e.g. Django's `views.py`/`serializers.py`/`urls.py`, NestJS's `.module.ts`). Optionally consults the project's own `ScanResult` to emit a non-blocking naming-consistency warning when generated code diverges from a convention the repository itself demonstrates.

### Architecture score

`archapi/validation/architecture_score.py` scores generated files against the detected genome (named, itemized checks — not a black box), surfaced to the user but not a gate on its own.

### GenerationResult

`archapi/types.py` — the structured result: plan, files, validation report, `policy_gate_pass`/`framework_validation_pass` captured separately, warnings.

### FileTransaction / atomic application

`archapi/generation/file_transaction.py` — `dry_run=True` (the CLI default) never touches the filesystem. When applying, every destination is validated up front (same path-safety checks as always), each file is written via a temp file + atomic rename so no single file is ever left torn, and if any write in the batch fails, everything the transaction has already written is rolled back: overwritten files restored to their exact original content, newly created files deleted, directories the transaction itself created removed if left empty. No git dependency — pure filesystem operations.

## CLI and configuration layers

`archapi/cli.py` and `archapi/config.py` sit above this pipeline, not inside it: the CLI resolves an `ArchAPIConfig` (precedence: explicit flag > `archapi.toml` > environment variable > default — see [`CONFIGURATION.md`](CONFIGURATION.md)) and constructs `ArchAPI` with it; core orchestration logic is identical whether invoked from the CLI or directly from Python.

## Evaluation layer

`evaluation/` (outside `archapi/`, not a runtime dependency) runs the same pipeline through a reproducible harness for comparative experiments (baseline vs. `archapi_retrieval`, deterministic vs. real-provider). See [`EVALUATION.md`](EVALUATION.md) and [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md).
