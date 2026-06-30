# ArchAPI

ArchAPI is a Python library for architecture-preserving REST API generation.

It scans an existing backend project, detects the framework, understands the project structure, plans a REST API, generates framework-specific files, validates the output, and writes files only when explicitly requested.

---

## Current Status

Current checkpoint: **Phase 3 complete**

Completed:

- Functional Python package
- Express TypeScript adapter
- FastAPI adapter
- Generic fallback adapter
- Framework detection
- Project scanning
- API architecture model
- Confidence scoring
- Low-confidence blocking
- Strict config mode
- REST intent planner
- Code generation
- Dry-run generation
- Safe apply
- Overwrite protection
- Cache and changed-file detection
- Secret scanner
- Context redaction
- Policy gate
- Architecture consistency score
- Command validation
- Unified regression test suite

---

## Supported Frameworks

Dedicated generation support currently exists for:

- Express TypeScript
- FastAPI

Other frameworks may be detected, but they currently use the generic fallback adapter.

---

## Installation

From the project root:

```bash
pip install -e .
