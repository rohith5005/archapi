from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from archapi.indexing.relevance_scorer import (
    _AUTH_REQUEST_KEYWORDS,
    _VALIDATION_REQUEST_KEYWORDS,
    RelevanceScorer,
    ScoredUnit,
)
from archapi.indexing.repository_index import RepositoryIndex
from archapi.types import APIPlan

# ---------------------------------------------------------------------------
# Deterministic context retrieval + budgeting (Phase 7D).
#
# Turns a RelevanceScorer ranking into a bounded, structured, explainable
# context selection:
#
#   RepositoryIndex + APIPlan -> RelevanceScorer -> ranked units
#       -> layer-aware per-category selection -> global char budget
#       -> RetrievedContext
#
# Deliberately kept out of PromptBuilder/the LLM path and out of
# ContextRedactor: this module preserves original snippets so security
# redaction can run once, later, over whatever actually gets assembled into
# an outbound prompt (Phase 7E). Not wired into ArchAPI/core.py yet.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextBudget:
    """
    Centralized retrieval budget defaults, so downstream phases (7E) never
    hardcode these as magic numbers. Two independent controls: a per-category
    item-count cap, and a shared global character budget applied afterward
    over the deduplicated selection.
    """
    routes: int = 2
    controllers: int = 2
    services: int = 2
    schemas: int = 2
    models: int = 1
    tests: int = 2
    auth_patterns: int = 1
    validation_patterns: int = 1
    global_char_budget: int = 12_000


DEFAULT_BUDGET = ContextBudget()


@dataclass
class RetrievedItem:
    path: str
    layer: str
    score: int
    reasons: List[str] = field(default_factory=list)
    snippet: str = ""


@dataclass
class RetrievedContext:
    routes: List[RetrievedItem] = field(default_factory=list)
    controllers: List[RetrievedItem] = field(default_factory=list)
    services: List[RetrievedItem] = field(default_factory=list)
    schemas: List[RetrievedItem] = field(default_factory=list)
    models: List[RetrievedItem] = field(default_factory=list)
    # Semantic views, not architectural layers: a unit can legitimately
    # appear here *and* in its primary category above (e.g. an authenticated
    # route file is both a "route" and an "auth pattern"). Middleware-layer
    # units (guards/permission checks) surface only through auth_patterns,
    # since they have no other primary bucket in this shape.
    auth_patterns: List[RetrievedItem] = field(default_factory=list)
    validation_patterns: List[RetrievedItem] = field(default_factory=list)
    tests: List[RetrievedItem] = field(default_factory=list)

    def all_items(self) -> List[RetrievedItem]:
        """
        Deduplicated flat view across all categories, by path. Use this --
        not the individual category lists -- when assembling the outbound
        context, so a snippet referenced from multiple semantic views is
        only transmitted once.
        """
        seen: Set[str] = set()
        items: List[RetrievedItem] = []
        for category in (
            self.routes, self.controllers, self.services, self.schemas,
            self.models, self.tests, self.auth_patterns, self.validation_patterns,
        ):
            for item in category:
                if item.path in seen:
                    continue
                seen.add(item.path)
                items.append(item)
        return items

    def total_snippet_chars(self) -> int:
        return sum(len(item.snippet) for item in self.all_items())


_LAYER_TO_CATEGORY = {
    "route": "routes",
    "controller": "controllers",
    "service": "services",
    "schema": "schemas",
    "model": "models",
    "test": "tests",
}


class ContextRetriever:
    """
    context = ContextRetriever().retrieve(request=request, plan=plan, index=index)
    """

    def __init__(self, budget: Optional[ContextBudget] = None):
        self.budget = budget or DEFAULT_BUDGET
        self._scorer = RelevanceScorer()

    def retrieve(self, request: str, plan: APIPlan, index: RepositoryIndex) -> RetrievedContext:
        scored = self._scorer.score(plan, index)
        eligible = [scored_unit for scored_unit in scored if scored_unit.score > 0]

        by_layer: Dict[str, List[ScoredUnit]] = {}
        for scored_unit in eligible:
            by_layer.setdefault(scored_unit.unit.layer, []).append(scored_unit)

        per_category_limits = {
            "routes": self.budget.routes,
            "controllers": self.budget.controllers,
            "services": self.budget.services,
            "schemas": self.budget.schemas,
            "models": self.budget.models,
            "tests": self.budget.tests,
        }

        selections: Dict[str, List[ScoredUnit]] = {
            category: by_layer.get(layer, [])[:limit]
            for layer, category in _LAYER_TO_CATEGORY.items()
            for limit in (per_category_limits[category],)
        }

        wants_auth = _mentions_any(request, _AUTH_REQUEST_KEYWORDS)
        wants_validation = _mentions_any(request, _VALIDATION_REQUEST_KEYWORDS)

        auth_candidates = [su for su in eligible if su.unit.auth_indicators]
        selections["auth_patterns"] = (
            auth_candidates[: self.budget.auth_patterns] if wants_auth else []
        )

        validation_candidates = [su for su in eligible if su.unit.validation_indicators]
        selections["validation_patterns"] = (
            validation_candidates[: self.budget.validation_patterns] if wants_validation else []
        )

        retained_paths = self._apply_global_char_budget(selections)

        def to_items(scored_units: List[ScoredUnit]) -> List[RetrievedItem]:
            return [
                RetrievedItem(
                    path=str(su.unit.path),
                    layer=su.unit.layer,
                    score=su.score,
                    reasons=list(su.reasons),
                    snippet=su.unit.snippet,
                )
                for su in scored_units
                if str(su.unit.path) in retained_paths
            ]

        return RetrievedContext(
            routes=to_items(selections["routes"]),
            controllers=to_items(selections["controllers"]),
            services=to_items(selections["services"]),
            schemas=to_items(selections["schemas"]),
            models=to_items(selections["models"]),
            auth_patterns=to_items(selections["auth_patterns"]),
            validation_patterns=to_items(selections["validation_patterns"]),
            tests=to_items(selections["tests"]),
        )

    def _apply_global_char_budget(self, selections: Dict[str, List[ScoredUnit]]) -> Set[str]:
        # Dedup by path first: a unit selected into two categories (e.g. a
        # route that is also an auth pattern) must only count once against
        # the shared budget, matching what all_items() will later transmit.
        unique: Dict[str, ScoredUnit] = {}
        for scored_units in selections.values():
            for su in scored_units:
                path = str(su.unit.path)
                if path not in unique:
                    unique[path] = su

        ordered = sorted(
            unique.values(),
            key=lambda su: (-su.score, su.unit.layer, str(su.unit.path)),
        )

        # Fixed priority order, greedy-skip on overflow: a candidate that
        # doesn't fit is skipped (not swapped in for a lower-priority one),
        # and earlier (higher-priority) inclusion decisions are never
        # revisited. This keeps selection monotonic in the budget -- a
        # higher-ranked item, once included, stays included for any larger
        # budget.
        retained: Set[str] = set()
        running_total = 0
        for su in ordered:
            size = len(su.unit.snippet)
            if running_total + size <= self.budget.global_char_budget:
                retained.add(str(su.unit.path))
                running_total += size

        return retained


def _mentions_any(text: Optional[str], keywords: Set[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)
