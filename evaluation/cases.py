"""
Phase 8B: evaluation case definitions.

A case is (framework, request, expected resource, a fixture-project
builder). Reuses the same fixture builders as the Phase 7F cross-framework
matrix and the Phase 7G real-provider script, so results stay directly
comparable across all three: the deterministic matrix (7F), the
preserved real-provider results (7G, evaluation/results/), and anything
this harness produces going forward.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.test_cross_framework_evaluation import (  # noqa: E402
    create_django_matrix_project,
    create_express_matrix_project,
    create_fastapi_matrix_project,
)


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    framework: str
    request: str
    expected_resource: str
    build_project: Callable[[Path], Path]


# The same three (framework, request) pairs used in the Phase 7G
# real-provider evaluation (see evaluation/results/phase7g_openai_6call.json
# and scripts/phase7g_real_provider_evaluation.py), so results stay
# directly comparable across provider modes and over time.
CASES: List[EvaluationCase] = [
    EvaluationCase(
        case_id="express_warranty_claim",
        framework="express-typescript",
        request="authenticated POST warranty claim API with validation",
        expected_resource="warranty",
        build_project=create_express_matrix_project,
    ),
    EvaluationCase(
        case_id="fastapi_shipment_status",
        framework="fastapi",
        request="PATCH shipment status API with validation",
        expected_resource="shipment",
        build_project=create_fastapi_matrix_project,
    ),
    EvaluationCase(
        case_id="django_invoice",
        framework="django-drf",
        request="POST invoice API",
        expected_resource="invoice",
        build_project=create_django_matrix_project,
    ),
]

_CASES_BY_ID = {case.case_id: case for case in CASES}


def get_case(case_id: str) -> EvaluationCase:
    try:
        return _CASES_BY_ID[case_id]
    except KeyError:
        raise KeyError(f"Unknown evaluation case_id: {case_id!r}") from None
