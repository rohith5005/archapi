"""
Phase 8B: the evaluation runner.

Given an EvaluationCase + context strategy + provider mode, runs ArchAPI
and returns a structured, JSON-serializable EvaluationResult.

Two independent axes:
  - context_mode  : "baseline" (PromptBuilder gets no retrieved_context --
                     isolates exactly the Phase 7 retrieval variable) vs.
                     "archapi_retrieval" (the real production path: index
                     -> ContextRetriever -> PromptBuilder).
  - provider_mode : "deterministic" (a fake, in-memory provider -- no
                     network, no cost; the default, and the only mode any
                     unit test may use) vs. "real_llm" (a real, billed
                     OpenAI call -- requires confirm_real_call=True as an
                     explicit, code-level opt-in *and* OPENAI_API_KEY to be
                     set; omitting either raises before any network
                     attempt is made).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from archapi import ArchAPI  # noqa: E402
from archapi.indexing.context_retriever import ContextRetriever  # noqa: E402
from archapi.indexing.repository_index import build_repository_index  # noqa: E402
from archapi.llm.errors import LLMParseError, LLMProviderError  # noqa: E402
from archapi.llm.prompt_builder import PromptBuilder  # noqa: E402
from archapi.llm.response_parser import ResponseParser  # noqa: E402
from archapi.security.policy_gate import PolicyGate  # noqa: E402
from archapi.validation.architecture_score import ArchitectureConsistencyScorer  # noqa: E402

from evaluation.cases import EvaluationCase  # noqa: E402
from evaluation.metrics import (  # noqa: E402
    EvaluationResult,
    auth_pattern_reused,
    classify_generated_layers,
    count_unnecessary_files,
    detected_resource,
    expected_layers_for,
    validation_pattern_reused,
)

DEFAULT_MODEL = "gpt-4o-mini"
_CONTEXT_MODES = ("baseline", "archapi_retrieval")
_PROVIDER_MODES = ("deterministic", "real_llm")


def _fake_files_for(case: EvaluationCase) -> list:
    """A minimal, framework-conformant file set for the given case's own
    framework -- so deterministic-mode runs genuinely exercise pass/fail
    validation instead of always failing on a generic, non-conformant
    naming scheme."""
    resource = case.expected_resource
    pascal = resource.capitalize()

    if case.framework == "fastapi":
        return [
            {"path": f"app/routers/{resource}_router.py", "content": f"# {pascal} route\n"},
            {"path": f"app/services/{resource}_service.py", "content": f"class {pascal}Service:\n    pass\n"},
            {"path": f"app/schemas/{resource}_schema.py", "content": f"class {pascal}Schema:\n    pass\n"},
            {"path": f"tests/test_{resource}.py", "content": "def test_x():\n    assert True\n"},
        ]
    if case.framework == "flask":
        return [
            {"path": f"app/routes/{resource}_routes.py", "content": f"# {pascal} route\n"},
            {"path": f"app/services/{resource}_service.py", "content": f"class {pascal}Service:\n    pass\n"},
            {"path": f"app/schemas/{resource}_schema.py", "content": f"class {pascal}Schema:\n    pass\n"},
            {"path": f"tests/test_{resource}.py", "content": "def test_x():\n    assert True\n"},
        ]
    if case.framework == "django-drf":
        app = f"{resource}s"
        return [
            {"path": f"{app}/views.py", "content": f"class {pascal}View:\n    pass\n"},
            {"path": f"{app}/serializers.py", "content": f"class {pascal}Serializer:\n    pass\n"},
            {"path": f"{app}/urls.py", "content": "urlpatterns = []\n"},
            # Flat per-app convention, matching django-admin startapp's own
            # default and validated by Phase 8A -- see
            # tests/test_validator_repository_consistency.py.
            {"path": f"{app}/tests.py", "content": "def test_x():\n    assert True\n"},
        ]
    if case.framework == "express-typescript":
        return [
            {"path": f"src/routes/{resource}.routes.ts", "content": "export {}\n"},
            {"path": f"src/controllers/{resource}.controller.ts", "content": "export {}\n"},
            {"path": f"src/services/{resource}.service.ts", "content": "export {}\n"},
            {"path": f"src/schemas/{resource}.schema.ts", "content": "export {}\n"},
            {"path": f"tests/{resource}.test.ts", "content": "export {}\n"},
        ]
    if case.framework == "nestjs":
        return [
            {"path": f"src/{resource}/{resource}.controller.ts", "content": "export {}\n"},
            {"path": f"src/{resource}/{resource}.service.ts", "content": "export {}\n"},
            {"path": f"src/{resource}/{resource}.module.ts", "content": "export {}\n"},
            {"path": f"src/{resource}/{resource}.dto.ts", "content": "export {}\n"},
            {"path": f"src/{resource}/{resource}.controller.spec.ts", "content": "export {}\n"},
        ]
    return [
        {"path": "generated/x_route.py", "content": "x = 1\n"},
        {"path": "generated/x_service.py", "content": "x = 1\n"},
        {"path": "generated/x_schema.py", "content": "x = 1\n"},
        {"path": "generated/test_x.py", "content": "def test_x(): assert True\n"},
    ]


def _fake_response_for(case: EvaluationCase) -> str:
    return json.dumps({
        "method": "POST",
        "path": f"/{case.expected_resource}s",
        "entities": [case.expected_resource.capitalize()],
        "layers": ["route", "service", "schema", "test"],
        "files": _fake_files_for(case),
    })


def _fake_provider(case: EvaluationCase) -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = _fake_response_for(case)
    return provider


def run_case(
    case: EvaluationCase,
    context_mode: str,
    provider_mode: str = "deterministic",
    model: str = DEFAULT_MODEL,
    project_root: Optional[Path] = None,
    confirm_real_call: bool = False,
) -> EvaluationResult:
    """
    Run one evaluation case and return a structured EvaluationResult.
    Always dry-run semantics -- generated files are validated/scored but
    never written to disk.
    """
    if context_mode not in _CONTEXT_MODES:
        raise ValueError(f"context_mode must be one of {_CONTEXT_MODES}, got {context_mode!r}")
    if provider_mode not in _PROVIDER_MODES:
        raise ValueError(f"provider_mode must be one of {_PROVIDER_MODES}, got {provider_mode!r}")

    if provider_mode == "real_llm" and not confirm_real_call:
        raise RuntimeError(
            "provider_mode='real_llm' requires confirm_real_call=True as an explicit, "
            "code-level opt-in. This makes a real, billed OpenAI API call."
        )

    owns_tempdir = project_root is None
    tempdir_ctx = tempfile.TemporaryDirectory() if owns_tempdir else None

    try:
        root = Path(tempdir_ctx.name) if owns_tempdir else project_root
        project = case.build_project(root)

        result = EvaluationResult(
            case_id=case.case_id,
            framework=case.framework,
            request=case.request,
            mode=context_mode,
            provider="openai" if provider_mode == "real_llm" else "fake",
            model=model,
            expected_layers=expected_layers_for(case.framework),
        )

        engine = ArchAPI(str(project))
        genome = engine.extract_genome()
        scan = engine.scan()
        maps = engine.build_maps()
        adapter = engine._adapter()
        plan_hint = adapter.plan_api(case.request, genome, maps)
        result.detected_resource = detected_resource(plan_hint)

        retrieved_context = None
        if context_mode == "archapi_retrieval":
            index = build_repository_index(scan, genome)
            retrieved_context = ContextRetriever().retrieve(
                request=case.request, plan=plan_hint, index=index
            )
            result.retrieved_paths = [item.path for item in retrieved_context.all_items()]

        prompt = PromptBuilder().build(
            case.request, genome, plan=plan_hint, retrieved_context=retrieved_context
        )
        prompt = engine._context_redactor.redact(prompt)

        if provider_mode == "real_llm":
            from archapi.llm.openai_provider import OpenAIProvider
            llm = OpenAIProvider(model=model)
        else:
            llm = _fake_provider(case)

        try:
            raw_response = llm.complete(prompt)
        except LLMProviderError as exc:
            result.errors.append(f"provider error: {exc}")
            return result

        try:
            plan, files = ResponseParser().parse(raw_response)
        except LLMParseError as exc:
            result.errors.append(f"parse error: {exc}")
            return result

        result.parse_success = True
        result.generated_paths = [str(f.path) for f in files]

        report = adapter.validate_generated_code(files, plan, genome, scan=scan)
        result.framework_validation_pass = report.success
        result.errors.extend(report.errors)
        result.warnings.extend(report.warnings)

        policy = PolicyGate().validate_files(files, plan)
        result.policy_gate_pass = policy.allowed
        result.errors.extend(policy.errors)
        result.warnings.extend(policy.warnings)

        result.generation_allowed = report.success and policy.allowed

        score = ArchitectureConsistencyScorer().score(files, genome)
        result.architecture_score = score.percentage

        result.generated_layers = classify_generated_layers(files, case.framework)
        result.unnecessary_file_count = count_unnecessary_files(files, case.framework, result.expected_layers)

        result.auth_pattern_reused = auth_pattern_reused(files, retrieved_context)
        result.validation_pattern_reused = validation_pattern_reused(files, retrieved_context)

        return result
    finally:
        if tempdir_ctx is not None:
            tempdir_ctx.cleanup()


def run_comparison(
    case: EvaluationCase,
    provider_mode: str = "deterministic",
    model: str = DEFAULT_MODEL,
    confirm_real_call: bool = False,
) -> Tuple[EvaluationResult, EvaluationResult]:
    """Run the same case in both context modes -- same case (so same
    request/framework/fixture), same provider_mode/model, only the context
    strategy differs. Returns (baseline, archapi_retrieval)."""
    baseline = run_case(
        case, "baseline", provider_mode=provider_mode, model=model, confirm_real_call=confirm_real_call
    )
    retrieval = run_case(
        case, "archapi_retrieval", provider_mode=provider_mode, model=model, confirm_real_call=confirm_real_call
    )
    return baseline, retrieval
