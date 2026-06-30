# Architecture

ArchAPI has these main layers:

1. Core orchestration
2. Framework detection
3. Framework adapters
4. REST planning
5. Code generation
6. Validation
7. Cache and indexing
8. Security

## Core

`archapi/core.py` contains the main `ArchAPI` class.

It coordinates framework detection, scanning, map building, architecture extraction, confidence scoring, planning, generation, validation, cache, and security checks.

## Frameworks

Framework logic is under `archapi/frameworks`.

Dedicated adapters:

- `archapi/frameworks/express_ts/adapter.py`
- `archapi/frameworks/fastapi_adapter.py`

Fallback adapter:

- `archapi/frameworks/generic.py`

## Planning

`archapi/planning/intent_planner.py` converts user requests into REST plans.

Example:

`Create POST API for product review`

becomes:

`POST /products/{product_id}/reviews`

## Validation

Validation includes generated-file checks, architecture scoring, command validation, and policy checks.

## Security

Security includes dry-run behavior, overwrite protection, low-confidence blocking, strict config mode, secret scanning, context redaction, and policy validation.
