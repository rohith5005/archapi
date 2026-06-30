# File Guide

## Root files

- `README.md`: project overview and quickstart
- `pyproject.toml`: Python package metadata
- `.gitignore`: local/generated file exclusions

## Main package

- `archapi/__init__.py`: public package export
- `archapi/core.py`: main orchestration class
- `archapi/types.py`: shared dataclasses

## Frameworks

- `archapi/frameworks/base.py`: adapter interface
- `archapi/frameworks/detector.py`: framework detection
- `archapi/frameworks/registry.py`: adapter registry
- `archapi/frameworks/generic.py`: fallback adapter
- `archapi/frameworks/express_ts/adapter.py`: Express TypeScript adapter
- `archapi/frameworks/fastapi_adapter.py`: FastAPI adapter

## Planning

- `archapi/planning/intent_planner.py`: REST planner
- `archapi/planning/task_dag.py`: task dependency model

## Indexing

- `archapi/indexing/cache.py`: cache and changed-file detection

## Security

- `archapi/security/secret_scanner.py`: secret scanner
- `archapi/security/context_redactor.py`: redactor
- `archapi/security/policy_gate.py`: policy checks

## Validation

- `archapi/validation/architecture_score.py`: architecture scoring
- `archapi/validation/basic_validators.py`: generated-file validation
- `archapi/validation/command_validator.py`: optional command validation

## Tests

- `tests/test_archapi_suite.py`: unified test suite
