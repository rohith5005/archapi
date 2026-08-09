#!/usr/bin/env python3
"""
Phase 7G: real OpenAI provider evaluation.

Standalone script -- intentionally NOT under tests/ and not named test_*.py,
so `python -m unittest` (and any test discovery) can never pick it up and
accidentally spend OpenAI credits.

Makes exactly 6 real, billed OpenAI API calls: 3 controlled A/B pairs
(baseline vs. ArchAPI retrieval-aware generation) across three
frameworks/requests. The 6-case matrix is hardcoded below and there is no
flag to expand it -- this script cannot silently balloon into a larger,
more expensive run.

For each pair, everything is held constant except the repository-context
strategy:
  - baseline          : PromptBuilder receives no retrieved_context at all
                         (architecture/genome/request/plan info only --
                         this isolates exactly the Phase 7 retrieval
                         variable, not Phase 5/6 architecture-awareness,
                         which both modes already have).
  - archapi_retrieval  : the real production path -- RepositoryIndex ->
                         ContextRetriever -> PromptBuilder, same as
                         ArchAPI._generate_with_llm in core.py.

Usage:
    export OPENAI_API_KEY="sk-..."
    python scripts/phase7g_real_provider_evaluation.py

    # Validate all plumbing (prompt construction, parsing, scoring, JSON
    # output) with zero API calls and zero cost, using a fake provider:
    python scripts/phase7g_real_provider_evaluation.py --dry-run

Never pass the API key as a CLI argument or hardcode it here -- it is only
ever read from the OPENAI_API_KEY environment variable (via OpenAIProvider)
and is never written to the result JSON or printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from archapi import ArchAPI  # noqa: E402
from archapi.indexing.context_retriever import ContextRetriever  # noqa: E402
from archapi.indexing.repository_index import (  # noqa: E402
    _AUTH_KEYWORDS,
    _VALIDATION_KEYWORDS,
    _match_keywords,
    build_repository_index,
)
from archapi.llm.errors import LLMParseError, LLMProviderError  # noqa: E402
from archapi.llm.prompt_builder import PromptBuilder  # noqa: E402
from archapi.llm.response_parser import ResponseParser  # noqa: E402
from archapi.mapping.layer_classifier import LayerClassifier  # noqa: E402
from archapi.security.policy_gate import PolicyGate  # noqa: E402
from archapi.validation.architecture_score import ArchitectureConsistencyScorer  # noqa: E402
from tests.test_cross_framework_evaluation import (  # noqa: E402
    create_django_matrix_project,
    create_express_matrix_project,
    create_fastapi_matrix_project,
)

MODEL = "gpt-4o-mini"
_EXPECTED_LAYERS = {"route", "controller", "service", "schema", "test"}

CASES = [
    {
        "framework": "express-typescript",
        "build": create_express_matrix_project,
        "request": "authenticated POST warranty claim API with validation",
    },
    {
        "framework": "fastapi",
        "build": create_fastapi_matrix_project,
        "request": "PATCH shipment status API with validation",
    },
    {
        "framework": "django-drf",
        "build": create_django_matrix_project,
        "request": "POST invoice API",
    },
]


@dataclass
class CallResult:
    framework: str
    request: str
    mode: str  # "baseline" | "archapi_retrieval"
    model: str
    retrieved_paths: List[str] = field(default_factory=list)
    generated_paths: List[str] = field(default_factory=list)
    generation_allowed: bool = False
    policy_gate_pass: bool = False
    framework_validation_pass: bool = False
    architecture_score: Optional[float] = None
    unnecessary_file_count: int = 0
    correct_layer_count: int = 0
    auth_pattern_reused: bool = False
    validation_pattern_reused: bool = False
    parse_success: bool = False
    error: Optional[str] = None


def _fake_provider() -> MagicMock:
    """Only used with --dry-run: validates the full pipeline (prompt
    construction through scoring) without any network call or cost."""
    provider = MagicMock()
    provider.complete.return_value = json.dumps({
        "method": "POST",
        "path": "/x",
        "entities": ["x"],
        "layers": ["route", "service", "schema", "test"],
        "files": [
            {"path": "generated/x_route.py", "content": "x = 1\n"},
            {"path": "generated/x_service.py", "content": "x = 1\n"},
            {"path": "generated/x_schema.py", "content": "x = 1\n"},
            {"path": "generated/test_x.py", "content": "def test_x(): assert True\n"},
        ],
    })
    return provider


def _score_generated_layers(files, framework: str) -> tuple[int, int]:
    """Deterministic layer/role coverage from generated file paths, via the
    same LayerClassifier used for indexing. "unnecessary" is intentionally
    a narrow, explicit definition: any layer generated more than once
    (duplicate coverage of the same role), plus any file that doesn't
    classify into one of the 5 expected roles at all -- not a judgment
    call about code quality."""
    classifier = LayerClassifier()
    layer_counts: Dict[str, int] = {}

    for generated_file in files:
        rel_path = Path(str(generated_file.path))
        try:
            classification = classifier.classify(rel_path, framework=framework)
            layer = classification.layer
        except ValueError:
            layer = "unknown"
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    correct_layer_count = sum(1 for layer in _EXPECTED_LAYERS if layer_counts.get(layer, 0) >= 1)
    unnecessary_file_count = sum(
        max(0, count - 1) for layer, count in layer_counts.items() if layer in _EXPECTED_LAYERS
    )
    unnecessary_file_count += sum(
        count for layer, count in layer_counts.items() if layer not in _EXPECTED_LAYERS
    )

    return correct_layer_count, unnecessary_file_count


def run_pipeline(project: Path, request: str, framework: str, mode: str, llm) -> CallResult:
    result = CallResult(framework=framework, request=request, mode=mode, model=MODEL)

    engine = ArchAPI(str(project))
    genome = engine.extract_genome()
    scan = engine.scan()
    maps = engine.build_maps()
    adapter = engine._adapter()
    plan_hint = adapter.plan_api(request, genome, maps)

    retrieved_context = None
    if mode == "archapi_retrieval":
        index = build_repository_index(scan, genome)
        retrieved_context = ContextRetriever().retrieve(request=request, plan=plan_hint, index=index)
        result.retrieved_paths = [item.path for item in retrieved_context.all_items()]

    prompt = PromptBuilder().build(request, genome, plan=plan_hint, retrieved_context=retrieved_context)
    prompt = engine._context_redactor.redact(prompt)

    try:
        raw_response = llm.complete(prompt)
    except LLMProviderError as exc:
        result.error = f"provider error: {exc}"
        return result

    try:
        plan, files = ResponseParser().parse(raw_response)
    except LLMParseError as exc:
        result.error = f"parse error: {exc}"
        return result

    result.parse_success = True
    result.generated_paths = [str(f.path) for f in files]

    report = adapter.validate_generated_code(files, plan, genome)
    result.framework_validation_pass = report.success

    policy = PolicyGate().validate_files(files, plan)
    result.policy_gate_pass = policy.allowed

    result.generation_allowed = report.success and policy.allowed

    score = ArchitectureConsistencyScorer().score(files, genome)
    result.architecture_score = score.percentage

    result.correct_layer_count, result.unnecessary_file_count = _score_generated_layers(files, framework)

    generated_text = "\n".join(f.content for f in files).lower()

    if retrieved_context is not None and retrieved_context.auth_patterns:
        retrieved_auth_indicators = set()
        for item in retrieved_context.auth_patterns:
            retrieved_auth_indicators.update(_match_keywords(item.snippet, _AUTH_KEYWORDS))
        result.auth_pattern_reused = any(kw in generated_text for kw in retrieved_auth_indicators)

    if retrieved_context is not None and retrieved_context.validation_patterns:
        retrieved_validation_indicators = set()
        for item in retrieved_context.validation_patterns:
            retrieved_validation_indicators.update(_match_keywords(item.snippet, _VALIDATION_KEYWORDS))
        result.validation_pattern_reused = any(kw in generated_text for kw in retrieved_validation_indicators)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate the full pipeline with a fake provider -- no API calls, no cost.",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Where to write the JSON results (default: a scratch temp file, path printed at the end).",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN: no OpenAI API calls will be made ===\n")
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            print(
                "ERROR: OPENAI_API_KEY is not set.\n"
                "  export OPENAI_API_KEY='sk-...'\n"
                "This script never accepts the key as a CLI argument or reads it from any file.",
                file=sys.stderr,
            )
            return 1

        confirm = input(
            f"This will make {len(CASES) * 2} real, billed OpenAI API calls "
            f"(model={MODEL}). Continue? [y/N] "
        )
        if confirm.strip().lower() != "y":
            print("Aborted.")
            return 1

    results: List[CallResult] = []

    with tempfile.TemporaryDirectory() as tmp:
        for case in CASES:
            project = case["build"](Path(tmp))

            for mode in ("baseline", "archapi_retrieval"):
                print(f"--- {case['framework']} | {mode} | \"{case['request']}\" ---")

                if args.dry_run:
                    llm = _fake_provider()
                else:
                    from archapi.llm.openai_provider import OpenAIProvider
                    llm = OpenAIProvider(model=MODEL)

                result = run_pipeline(project, case["request"], case["framework"], mode, llm)
                results.append(result)

                if result.error:
                    print(f"  ERROR: {result.error}")
                else:
                    print(
                        f"  generation_allowed={result.generation_allowed} "
                        f"policy_gate={result.policy_gate_pass} "
                        f"framework_validation={result.framework_validation_pass} "
                        f"architecture_score={result.architecture_score}"
                    )

    output_path = args.output
    if output_path is None:
        fd_dir = Path(tempfile.gettempdir())
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = fd_dir / f"phase7g_results_{timestamp}.json"

    output_path.write_text(json.dumps([asdict(r) for r in results], indent=2))

    print("\n" + "=" * 100)
    print(f"{'framework':<20} {'mode':<18} {'allowed':<8} {'policy':<7} {'fw_valid':<9} {'arch%':<7} {'unnec':<6} {'layers':<7} {'auth':<6} {'valid':<6}")
    for r in results:
        print(
            f"{r.framework:<20} {r.mode:<18} {str(r.generation_allowed):<8} "
            f"{str(r.policy_gate_pass):<7} {str(r.framework_validation_pass):<9} "
            f"{str(r.architecture_score):<7} {r.unnecessary_file_count:<6} "
            f"{r.correct_layer_count:<7} {str(r.auth_pattern_reused):<6} {str(r.validation_pattern_reused):<6}"
        )
    print("=" * 100)
    print(f"\nFull results written to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
