#!/usr/bin/env bash
set -e

if command -v python >/dev/null 2>&1; then
  PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "ERROR: python/python3 not found"
  exit 127
fi

if [ ! -f "pyproject.toml" ] || [ ! -d "archapi" ]; then
  echo "ERROR: Run this from archapi-lib project root."
  exit 1
fi

echo "Cleaning local/generated files..."
rm -f project_structure_full.txt
rm -rf docs/exported
rm -rf archapi.egg-info
rm -rf sample_projects/express_basic/.archapi
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name "*.pyc" -delete
find . -name ".DS_Store" -delete

echo "Creating docs..."
mkdir -p docs
mkdir -p tests
mkdir -p examples

cat > README.md <<'EOF'
# ArchAPI

ArchAPI is a Python library for architecture-preserving REST API generation.

It scans an existing backend project, detects the framework, understands the project structure, plans a REST API, generates framework-specific files, validates the output, and writes files only when explicitly requested.

## Current Status

Current checkpoint: Phase 3 complete.

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

## Supported Frameworks

Dedicated generation support currently exists for:

- Express TypeScript
- FastAPI

Other frameworks may be detected, but they currently use the generic fallback adapter.

## Installation

```bash
pip install -e .