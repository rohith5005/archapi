"""
Phase 8B: the structured evaluation record and the pure, deterministic
metric functions that populate it.

Every metric here is an objective, measurable signal (did framework
validation pass, how many layers were covered, did generated code reuse an
existing auth/validation pattern) -- not a subjective quality judgment.
Subjective human/LLM judging, if added later, should be a separate,
clearly-labeled evaluation layer, not mixed into these fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from archapi.indexing.context_retriever import RetrievedContext
from archapi.indexing.repository_index import _AUTH_KEYWORDS, _VALIDATION_KEYWORDS, _match_keywords
from archapi.mapping.layer_classifier import LayerClassifier
from archapi.types import APIPlan, GeneratedFile

# Per-framework expected architectural layers -- the roles each framework
# adapter's own deterministic generator and structural validator treat as
# required, expressed via the shared LayerClassifier taxonomy (Phase 7B)
# rather than a framework-specific suffix list.
EXPECTED_LAYERS_BY_FRAMEWORK: Dict[str, Tuple[str, ...]] = {
    "fastapi": ("route", "service", "schema", "test"),
    "flask": ("route", "service", "schema", "test"),
    "django-drf": ("route", "controller", "schema", "test"),
    "express-typescript": ("route", "controller", "service", "schema", "test"),
    "nestjs": ("controller", "service", "schema", "test"),
}
_DEFAULT_EXPECTED_LAYERS = ("route", "service", "schema", "test")

_classifier = LayerClassifier()


@dataclass
class EvaluationResult:
    """
    A single case's evaluation outcome. Every field is either plain
    metadata or an objective, measurable signal -- deliberately no field
    for raw prompt text, repository snippet content, or any credential, so
    the object is always safe to serialize and share.
    """

    case_id: str
    framework: str
    request: str
    mode: str  # "baseline" | "archapi_retrieval"
    provider: str  # "fake" | "openai"
    model: str

    detected_resource: str = ""

    retrieved_paths: List[str] = field(default_factory=list)
    generated_paths: List[str] = field(default_factory=list)

    parse_success: bool = False
    generation_allowed: bool = False
    policy_gate_pass: bool = False
    framework_validation_pass: bool = False

    architecture_score: Optional[float] = None

    auth_pattern_reused: bool = False
    validation_pattern_reused: bool = False

    expected_layers: List[str] = field(default_factory=list)
    generated_layers: List[str] = field(default_factory=list)

    unnecessary_file_count: int = 0

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "framework": self.framework,
            "request": self.request,
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "detected_resource": self.detected_resource,
            "retrieved_paths": list(self.retrieved_paths),
            "generated_paths": list(self.generated_paths),
            "parse_success": self.parse_success,
            "generation_allowed": self.generation_allowed,
            "policy_gate_pass": self.policy_gate_pass,
            "framework_validation_pass": self.framework_validation_pass,
            "architecture_score": self.architecture_score,
            "auth_pattern_reused": self.auth_pattern_reused,
            "validation_pattern_reused": self.validation_pattern_reused,
            "expected_layers": list(self.expected_layers),
            "generated_layers": list(self.generated_layers),
            "unnecessary_file_count": self.unnecessary_file_count,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationResult":
        return cls(**data)


def detected_resource(plan_hint: APIPlan) -> str:
    return plan_hint.entities[-1].lower() if plan_hint.entities else ""


def expected_layers_for(framework: str) -> List[str]:
    return list(EXPECTED_LAYERS_BY_FRAMEWORK.get(framework, _DEFAULT_EXPECTED_LAYERS))


def _classify(path: Path, framework: str) -> Optional[str]:
    try:
        return _classifier.classify(path, framework=framework).layer
    except ValueError:
        # Malformed/absolute generated path -- not a layer-classification
        # concern here; PolicyGate is the actual gate for that.
        return None


def classify_generated_layers(files: Sequence[GeneratedFile], framework: str) -> List[str]:
    """Distinct architectural layers present among generated files, per the
    same LayerClassifier used for repository indexing and validation."""
    layers: Set[str] = set()
    for generated_file in files:
        layer = _classify(Path(str(generated_file.path)), framework)
        if layer is not None:
            layers.add(layer)
    return sorted(layers)


def count_unnecessary_files(
    files: Sequence[GeneratedFile],
    framework: str,
    expected_layers: Sequence[str],
) -> int:
    """
    Files beyond one-per-expected-layer, plus any file that doesn't
    classify into an expected role at all. A narrow, explicit definition
    (duplicate-role or off-role file count), not a code-quality judgment.
    """
    expected = set(expected_layers)
    layer_counts: Dict[str, int] = {}

    for generated_file in files:
        layer = _classify(Path(str(generated_file.path)), framework) or "unknown"
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    unnecessary = sum(max(0, count - 1) for layer, count in layer_counts.items() if layer in expected)
    unnecessary += sum(count for layer, count in layer_counts.items() if layer not in expected)
    return unnecessary


def _retrieved_keyword_indicators(
    items,
    keyword_set: Tuple[str, ...],
) -> Set[str]:
    indicators: Set[str] = set()
    for item in items:
        indicators.update(_match_keywords(item.snippet, keyword_set))
    return indicators


def auth_pattern_reused(
    files: Sequence[GeneratedFile],
    retrieved_context: Optional[RetrievedContext],
) -> bool:
    """Whether generated code reuses one of the same auth-indicator
    keywords found in the retrieved auth-pattern example(s) -- an
    objective textual-overlap signal, not a semantic judgment."""
    if retrieved_context is None or not retrieved_context.auth_patterns:
        return False
    indicators = _retrieved_keyword_indicators(retrieved_context.auth_patterns, _AUTH_KEYWORDS)
    if not indicators:
        return False
    generated_text = "\n".join(f.content for f in files).lower()
    return any(keyword in generated_text for keyword in indicators)


def validation_pattern_reused(
    files: Sequence[GeneratedFile],
    retrieved_context: Optional[RetrievedContext],
) -> bool:
    """Same signal as auth_pattern_reused, for the validation-pattern
    example(s)."""
    if retrieved_context is None or not retrieved_context.validation_patterns:
        return False
    indicators = _retrieved_keyword_indicators(retrieved_context.validation_patterns, _VALIDATION_KEYWORDS)
    if not indicators:
        return False
    generated_text = "\n".join(f.content for f in files).lower()
    return any(keyword in generated_text for keyword in indicators)
