#!/usr/bin/env bash
# scripts/test_openai_llm.sh
#
# Live integration test for ArchAPI LLM mode using the OpenAI provider.
# Requires: OPENAI_API_KEY to be set in the environment.
#
# Usage:
#   export OPENAI_API_KEY="sk-..."
#   ./scripts/test_openai_llm.sh
#
# Optional: override model (default: gpt-4o-mini)
#   LLM_MODEL=gpt-4o ./scripts/test_openai_llm.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMPLE_PROJECT="$PROJECT_ROOT/sample_projects/express_basic"
LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}"

echo "=========================================="
echo "  ArchAPI LLM Integration Test"
echo "  Model : $LLM_MODEL"
echo "  Project: $SAMPLE_PROJECT"
echo "=========================================="

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "ERROR: OPENAI_API_KEY is not set."
    echo "  export OPENAI_API_KEY='sk-...'"
    exit 1
fi

if [[ ! -d "$SAMPLE_PROJECT" ]]; then
    echo "ERROR: Sample project not found at $SAMPLE_PROJECT"
    echo "  Run: python -c \"from tests.test_archapi_suite import create_express_project; ...\""
    exit 1
fi

cd "$PROJECT_ROOT"

python - <<PYTHON
import os
import sys
from pathlib import Path
from archapi import ArchAPI

project = Path("$SAMPLE_PROJECT")
model   = "$LLM_MODEL"

print(f"\\nInitialising ArchAPI with LLM mode (model={model})...")

engine = ArchAPI(
    str(project),
    use_llm=True,
    llm_model=model,
)

detection = engine.detect_framework()
print(f"Detected framework : {detection.framework}  (confidence={detection.confidence})")

print("\\nCalling generate_api() — dry_run=True ...")
result = engine.generate_api(
    "Create authenticated POST API for user refund request",
    dry_run=True,
)

print(f"\\nPlan method : {result.plan.method}")
print(f"Plan path   : {result.plan.path}")
print(f"Files count : {len(result.files)}")
print(f"Validation  : {'PASSED' if result.validation_report.success else 'FAILED'}")

if result.validation_report.errors:
    print(f"Errors      : {result.validation_report.errors}")

if result.warnings:
    print(f"Warnings    : {result.warnings}")

print("\\nGenerated files:")
for f in result.files:
    print(f"  {f.path}")

if not result.validation_report.success:
    sys.exit(1)

print("\\n✅  LLM integration test PASSED")
PYTHON
