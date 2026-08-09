# Security Measures

ArchAPI includes deterministic safety controls at every stage where it reads from or writes to a real filesystem, and where it sends repository content to an external LLM provider. These are safeguards appropriate for a code-generation tool, not a formal sandbox — see Limitations.

## Before anything reaches the LLM

### Context redaction

`archapi/security/context_redactor.py`. Redacts secret-shaped values (API key assignments, tokens, secrets, private key blocks, AWS-style access keys) from the fully assembled prompt exactly once, immediately before the provider call — after retrieval and prompt construction, so there is one single, auditable enforcement point rather than redaction scattered across the pipeline. Retrieval and prompt rendering both preserve original (unredacted) snippets by design; redaction is the final step, not an early filter that could be bypassed by a later stage re-including raw content.

### Secret scanner

`archapi/security/secret_scanner.py`. Scans the local project for likely secrets (API keys, tokens, private keys, AWS-style keys) independent of generation, available via `ArchAPI.scan_secrets()`. Explicitly documented as a first safety layer, not a replacement for a dedicated tool like Gitleaks or TruffleHog.

## Before generated output is accepted

### PolicyGate

`archapi/security/policy_gate.py`. The output safety gate shared by both the deterministic and LLM generation paths, run on every generated file before it can be applied:

- **Absolute-path rejection** — refuses any generated path that is absolute.
- **Path traversal rejection** — refuses any generated path containing `..`.
- **Project-root containment** — every resolved target must remain inside the project root; enforced independently a second time at apply time (see below) as defense in depth.
- **Protected files/directories** — refuses writes to `.env`/`.env.local`/`.env.production`, private key files (`id_rsa`, `id_ed25519`), and paths inside protected directories (`.git`, `.venv`, `node_modules`, `.archapi`, `dist`, `build`, `coverage`, `__pycache__`, `vendor`, `target`).
- **Bootstrap/config controls** — refuses writes to dependency/config files (`package.json`, `requirements.txt`, `pyproject.toml`, `Dockerfile`, etc.) and application bootstrap/entry-point files (`main.py`, `app.py`, `settings.py`, `manage.py`, `server.ts`, `index.ts`, etc.) — ArchAPI generates new API layer code, not infrastructure or dependency changes.
- **Unrequested middleware rejection** — refuses a middleware/permission-guard file unless the plan explicitly declared a `middleware` layer.
- **Generated-secret detection** — scans generated file *content* (not just paths) against the same secret patterns the secret scanner uses, refusing a file whose content looks like it contains a credential.
- **Empty/duplicate-file rejection.**

### Framework validation

Each framework adapter's `validate_generated_code()` (`archapi/frameworks/*_adapter.py`) checks structural conformance — required architectural layers present, no empty files — using the shared `LayerClassifier` for checks that have legitimate real-world naming variance (e.g. test-file naming: `test_x.py` vs. `x_test.py` vs. a bare `tests.py` are all recognized, generalized in Phase 8A after a real failure exposed a hard-coded single-pattern check; see [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md)), and exact-match checks only where a framework genuinely has no realistic alternative (Django's `views.py`/`serializers.py`/`urls.py`, NestJS's `.module.ts`). Independently and optionally, it can emit a non-blocking naming-consistency warning when generated code diverges from a convention the project's own existing files demonstrate.

### Architecture score

`archapi/validation/architecture_score.py` — informational, itemized structural scoring surfaced to the user. Not a safety gate on its own; low scores are surfaced as a warning, not a rejection.

## Before anything is written to disk

### Dry-run default

`generate_api(dry_run=True)` is the default on every code path — the CLI (`archapi generate`), the Python API, and the evaluation harness. Nothing is written unless the caller/user opts in.

### Explicit `--apply`

The CLI requires `--apply` (an explicit, separate flag) to write anything; there is no flag combination that writes by default.

### Atomic file replacement and rollback

`archapi/generation/file_transaction.py` (`FileTransaction`), introduced in Phase 8D. Every destination is validated up front (the same absolute-path/traversal/create-vs-overwrite checks described above, run again as the last line of defense independent of whatever validation ran upstream). Each individual file is written via a temp file in the same directory plus an atomic `os.replace()`, so a single file is never left torn — either it has the full new content or it is untouched. If any write in a multi-file batch fails, everything the transaction has already written in that run is rolled back: files that existed before are restored to their exact original content, newly created files are deleted, and any directories the transaction itself created are removed if left empty (directories that pre-existed, or still hold unrelated content, are never touched or removed). This has no dependency on git — it works on an uncommitted repository, a non-git project, or files that were never tracked.

A blocked PolicyGate or framework-validation result is never applied, even with `--apply`: `apply()` is only called when validation succeeded, and `FileTransaction`'s own checks are a second, independent enforcement of the same path constraints.

## Repository/CI level

### CI secret scanning

`.github/workflows/test.yml` includes a dedicated job that greps tracked files for key-*shaped* values (a prefix followed by a long continuous alphanumeric run, matching real OpenAI key formats) rather than the `OPENAI_API_KEY` environment-variable name — so documentation or code that merely references the variable is never flagged, while an actual committed key would be. `.gitignore` excludes `.env`, `.archapi/`, build artifacts, and transaction temp files (`*.archapi-tmp`) so they can never be accidentally committed in the first place.

### No accidental paid LLM calls

The deterministic test suite (`python -m unittest discover -s tests -v`) never requires `OPENAI_API_KEY` and never makes a real network call — verified by CI, which sets no such key anywhere in the test job. The evaluation harness's `real_llm` provider mode (`evaluation/runner.py`) requires an explicit, code-level `confirm_real_call=True` in addition to the key being present; omitting it raises before any network attempt. The standalone real-provider script (`scripts/phase7g_real_provider_evaluation.py`) lives outside `tests/` specifically so `unittest` discovery can never invoke it.

## Limitations

These are deterministic, testable safeguards — not a formal sandbox, static analysis engine, or dependency-vulnerability scanner.

- ArchAPI does not execute generated code as part of validation. Structural/naming checks and secret-pattern matching do not substitute for a security review of generated logic.
- The secret scanner and generated-secret detection are pattern-based (regex) and can miss secrets that don't match a known shape, or in principle flag a non-secret that happens to match one.
- PolicyGate's protected-path and bootstrap-file lists are fixed sets reflecting common conventions across the frameworks ArchAPI supports; an unusual project layout could have sensitive files PolicyGate doesn't know to protect.
- `strict_validation` (see [`CONFIGURATION.md`](CONFIGURATION.md)) only ever adds caution — escalating non-fatal warnings to errors — and has no effect on PolicyGate or framework-validation errors, which cannot be disabled by any configuration, CLI flag, or environment variable. There is intentionally no `--skip-safety` / `--disable-policy-gate` / `--force-unsafe` option.
- Generated code always requires human review before merging; dry-run-by-default and the CLI's explicit `--apply` boundary exist specifically to make that review step unavoidable, not to replace it.

Recommended additional hardening for production use beyond what ArchAPI itself provides: static analysis / SAST on generated code, dependency vulnerability scanning, and mandatory human code review before merge.
