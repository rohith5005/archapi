from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from archapi.indexing.repository_index import IndexedUnit, RepositoryIndex
from archapi.types import APIPlan

# ---------------------------------------------------------------------------
# Deterministic, explainable relevance scoring (Phase 7C).
#
# Given an APIPlan and a RepositoryIndex, assigns every candidate unit a
# score plus a list of human-readable reasons. No embeddings, no fuzzy
# external libraries, no LLM calls -- every signal is exact/normalized token
# overlap or simple keyword detection over the plan's own request text,
# computed locally and reproducibly.
# ---------------------------------------------------------------------------

# Example point values -- a hand-tuned, explainable model, not a learned
# one. Reweight as empirical retrieval-quality evidence accumulates in
# later phases (7F/7G).
_ENTITY_MATCH_POINTS = 30
_LAYER_MATCH_POINTS = 20
_HTTP_METHOD_MATCH_POINTS = 15
_TOKEN_SIMILARITY_POINTS = 12
_AUTH_MATCH_POINTS = 10
_VALIDATION_MATCH_POINTS = 10
_ROUTE_PATH_SIMILARITY_POINTS = 5
_ROUTE_PATH_SIMILARITY_MAX = 10
_TEST_RELEVANCE_POINTS = 8

_AUTH_REQUEST_KEYWORDS = {
    "auth", "authenticated", "authentication", "authorize", "authorized",
    "authorization", "login", "token", "jwt", "permission", "secure",
}
_VALIDATION_REQUEST_KEYWORDS = {"valid", "validate", "validated", "validation"}

_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_PATH_PARAM_RE = re.compile(r"[:{<][^/}>]*[}>]?")


@dataclass
class ScoredUnit:
    unit: IndexedUnit
    score: int
    reasons: List[str] = field(default_factory=list)


class RelevanceScorer:
    """
    Scores every unit in a RepositoryIndex against an APIPlan.

    Returns results sorted highest-score-first, with ties broken by
    (layer, path) for fully deterministic, reproducible ranking.
    """

    def score(self, plan: APIPlan, index: RepositoryIndex) -> List[ScoredUnit]:
        resource_tokens = self._resource_tokens(plan)
        requested_layers = {layer.lower() for layer in (plan.layers or [])}
        method = (plan.method or "").upper()
        plan_path_segments = self._path_segments(plan.path)
        wants_auth = self._mentions_any(plan.request, _AUTH_REQUEST_KEYWORDS)
        wants_validation = self._mentions_any(plan.request, _VALIDATION_REQUEST_KEYWORDS)

        scored: List[ScoredUnit] = []
        for unit in index.units:
            points = 0
            reasons: List[str] = []

            entity_matches = resource_tokens & set(unit.entity_terms)
            if entity_matches:
                points += _ENTITY_MATCH_POINTS
                reasons.append(f"resource match: {', '.join(sorted(entity_matches))}")

            if unit.layer in requested_layers:
                points += _LAYER_MATCH_POINTS
                reasons.append(f"architectural layer match: {unit.layer}")

            if method and method in unit.http_methods:
                points += _HTTP_METHOD_MATCH_POINTS
                reasons.append(f"HTTP method match: {method}")

            symbol_tokens = self._symbol_tokens(unit)
            token_matches = (resource_tokens & symbol_tokens) - entity_matches
            if token_matches:
                points += _TOKEN_SIMILARITY_POINTS
                reasons.append(
                    f"symbol/token similarity: {', '.join(sorted(token_matches))}"
                )

            if wants_auth and unit.auth_indicators:
                points += _AUTH_MATCH_POINTS
                reasons.append("authentication pattern match")

            if wants_validation and unit.validation_indicators:
                points += _VALIDATION_MATCH_POINTS
                reasons.append("validation pattern match")

            route_overlap = self._route_path_overlap(plan_path_segments, unit.route_paths)
            if route_overlap:
                path_points = min(
                    _ROUTE_PATH_SIMILARITY_POINTS * len(route_overlap),
                    _ROUTE_PATH_SIMILARITY_MAX,
                )
                points += path_points
                reasons.append(f"route path similarity: {', '.join(sorted(route_overlap))}")

            if unit.is_test and entity_matches:
                points += _TEST_RELEVANCE_POINTS
                reasons.append("test relevance: covers matched resource")

            scored.append(ScoredUnit(unit=unit, score=points, reasons=reasons))

        return sorted(scored, key=lambda scored_unit: (
            -scored_unit.score, scored_unit.unit.layer, str(scored_unit.unit.path)
        ))

    def _resource_tokens(self, plan: APIPlan) -> Set[str]:
        tokens: Set[str] = set()
        for entity in plan.entities or []:
            lowered = entity.lower()
            tokens.add(lowered)
            tokens.add(_normalize_token(lowered))
        return tokens

    def _symbol_tokens(self, unit: IndexedUnit) -> Set[str]:
        tokens: Set[str] = set()
        for symbol in unit.symbols:
            for token in _tokenize(symbol.lstrip("@")):
                tokens.add(token)
                tokens.add(_normalize_token(token))
        return tokens

    def _mentions_any(self, text: Optional[str], keywords: Set[str]) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(keyword in lowered for keyword in keywords)

    def _path_segments(self, path: Optional[str]) -> Set[str]:
        if not path:
            return set()
        normalized = _PATH_PARAM_RE.sub("", path)
        return {segment.lower() for segment in normalized.split("/") if segment}

    def _route_path_overlap(self, plan_segments: Set[str], route_paths: List[str]) -> Set[str]:
        overlap: Set[str] = set()
        for route_path in route_paths:
            overlap |= (plan_segments & self._path_segments(route_path))
        return overlap


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for chunk in _TOKEN_SPLIT_RE.split(text):
        if not chunk:
            continue
        for sub in _CAMEL_SPLIT_RE.split(chunk):
            if sub:
                tokens.append(sub.lower())
    return tokens


def _normalize_token(token: str) -> str:
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token
