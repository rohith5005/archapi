#!/usr/bin/env bash
set -e

echo "Running ArchAPI full test suite..."

python -m compileall archapi
python -m unittest tests.test_archapi_suite -v

echo ""
echo "All ArchAPI tests passed."
