from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Deterministic, repository-relative architectural layer classification
# (Phase 7B).
#
# Classification is based entirely on the path *relative to the scanned
# project root* and is token-based (path segments and filename tokens split
# on non-alphanumeric boundaries and camelCase), never raw substring search
# over a full path string. This avoids the class of bug where a project root
# directory name (e.g. "identity-service") accidentally embeds a layer
# keyword ("entity", "service") and distorts classification of every file
# beneath it.
#
# Precedence: the file's own filename together with its *immediate* parent
# directory are the strongest, most local signal and are checked first, in
# structural-signal-before-weaker-signal rule order (test > middleware >
# route > controller > service > schema > model). Only if neither the
# filename nor the immediate parent match anything does classification fall
# back to walking further ancestor directories, nearest first. Ancestors
# beyond the immediate parent — including the project root's own name — are
# therefore always the weakest, last-resort signal.
# ---------------------------------------------------------------------------

_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_CONFIG_FILENAMES = {
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock",
    "poetry.lock", "setup.py", "setup.cfg", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "tsconfig.json",
    ".npmrc", "Makefile", "go.mod", "pom.xml", "build.gradle",
    "composer.json", "Gemfile",
}

_TEST_TOKENS = {"test", "tests", "spec", "specs", "__tests__"}
_MIDDLEWARE_TOKENS = {
    "middleware", "guard", "guards", "interceptor", "interceptors",
    "permission", "permissions",
}
_ROUTE_TOKENS = {
    "route", "routes", "router", "routers", "url", "urls",
    "endpoint", "endpoints",
}
_CONTROLLER_TOKENS = {
    "controller", "controllers", "handler", "handlers",
    "view", "views", "viewset", "viewsets",
}
_SERVICE_TOKENS = {"service", "services"}
_SCHEMA_TOKENS = {"schema", "schemas", "serializer", "serializers", "dto", "dtos"}
_MODEL_TOKENS = {"model", "models", "entity", "entities"}

# Precedence order: structural/strong signals first, weaker keyword signals
# last. A file inside a test directory or matching a test filename
# convention must classify as "test" even if it also mentions e.g. "service".
_LAYER_RULES: Tuple[Tuple[str, set], ...] = (
    ("test", _TEST_TOKENS),
    ("middleware", _MIDDLEWARE_TOKENS),
    ("route", _ROUTE_TOKENS),
    ("controller", _CONTROLLER_TOKENS),
    ("service", _SERVICE_TOKENS),
    ("schema", _SCHEMA_TOKENS),
    ("model", _MODEL_TOKENS),
)


@dataclass
class LayerClassification:
    layer: str
    reason: str
    matched_token: Optional[str] = None


class LayerClassifier:
    """
    Single classification authority for architectural layer assignment.

    Usage:
        classification = LayerClassifier().classify(relative_path, framework=framework)
        classification.layer  # "route" | "controller" | "service" | "schema"
                               # | "model" | "middleware" | "test" | "config"
                               # | "unknown"

    ``framework`` is accepted for forward compatibility (framework adapters
    may eventually provide hints) but is not used to branch logic here —
    Phase 7's generic retrieval engine must not encode framework-specific
    assumptions.
    """

    def classify(
        self,
        relative_path: Union[str, Path],
        framework: Optional[str] = None,
    ) -> LayerClassification:
        path = Path(relative_path)

        if path.is_absolute():
            raise ValueError(
                "LayerClassifier requires a path relative to the scanned "
                f"project root, got an absolute path: {path}"
            )

        filename = path.name
        if filename in _CONFIG_FILENAMES:
            return LayerClassification(
                layer="config",
                reason=f"Exact config filename match: {filename}",
                matched_token=filename,
            )

        name_tokens = _tokenize(path.stem)
        parents = [parent for parent in path.parents if str(parent) != "."]

        immediate_dir_tokens = _tokenize(parents[0].name) if parents else []
        tier1_tokens = immediate_dir_tokens + name_tokens

        result = self._match_rules(tier1_tokens, "immediate directory/filename")
        if result is not None:
            return result

        for parent in parents[1:]:
            dir_tokens = _tokenize(parent.name)
            result = self._match_rules(dir_tokens, f"ancestor directory '{parent.name}'")
            if result is not None:
                return result

        return LayerClassification(
            layer="unknown",
            reason="No structural or keyword signal matched any known layer",
        )

    def _match_rules(self, tokens: List[str], source: str) -> Optional[LayerClassification]:
        for layer, candidates in _LAYER_RULES:
            matched = _first_match(tokens, candidates)
            if matched:
                return LayerClassification(
                    layer=layer,
                    reason=f"token '{matched}' ({source}) matched {layer} layer",
                    matched_token=matched,
                )
        return None


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for chunk in _TOKEN_SPLIT_RE.split(text):
        if not chunk:
            continue
        for sub in _CAMEL_SPLIT_RE.split(chunk):
            if sub:
                tokens.append(sub.lower())
    return tokens


def _first_match(tokens: List[str], candidates: set) -> Optional[str]:
    for token in tokens:
        if token in candidates:
            return token
    return None
