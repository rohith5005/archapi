from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

from archapi.types import APIGenome, ScanResult

# ---------------------------------------------------------------------------
# Deterministic, local repository indexing (Phase 7A).
#
# This module reads already-scanned source files and extracts lightweight,
# regex-based signals (symbols, imports, HTTP methods/route paths, entity
# terms, auth/validation indicators) into a searchable, in-memory index.
#
# It is intentionally standalone: it consumes an existing ScanResult and does
# not touch ArchAPI, PromptBuilder, framework adapters, or Phase 6 security
# code. No network calls, no embeddings, no persistence.
# ---------------------------------------------------------------------------

_MAX_SOURCE_FILE_BYTES = 200_000
_MAX_SNIPPET_CHARS = 800

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}

_RECOGNIZED_SUFFIXES = set(_LANGUAGE_BY_SUFFIX)

# Reuse ScanResult's existing bucket membership as the initial layer signal
# rather than re-classifying files from scratch.
_LAYER_BY_BUCKET = (
    ("routes", "route"),
    ("controllers", "controller"),
    ("services", "service"),
    ("models", "model"),
    ("schemas", "schema"),
    ("middleware", "middleware"),
    ("tests", "test"),
)

_CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)
_METHOD_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*"
    r"(?:async\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)\s*(?::\s*[^{;=]+)?\{",
    re.MULTILINE,
)
_METHOD_KEYWORD_EXCLUSIONS = {
    "if", "for", "while", "switch", "catch", "function", "constructor", "else",
}
_DECORATOR_RE = re.compile(r"^\s*@([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)

_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w\.]+)\s+import\s+[^\n]+|import\s+([\w\.]+))", re.MULTILINE
)
_JS_IMPORT_RE = re.compile(
    r"""^\s*import\s+.*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

_DECORATOR_METHOD_RE = re.compile(
    r"@(?:[A-Za-z_][A-Za-z0-9_]*\.)?(get|post|put|patch|delete)\s*\(\s*(?:['\"]([^'\"]*)['\"])?",
    re.IGNORECASE,
)
_CALL_METHOD_RE = re.compile(
    r"\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE
)
_FLASK_ROUTE_RE = re.compile(
    r"\.route\(\s*['\"]([^'\"]+)['\"]\s*,\s*methods\s*=\s*\[([^\]]*)\]"
)
_DRF_METHOD_DEF_RE = re.compile(
    r"^\s*def\s+(get|post|put|patch|delete)\s*\(\s*self\s*,\s*request\b", re.MULTILINE
)

_AUTH_KEYWORDS = (
    "auth", "jwt", "permission", "guard", "bearer", "oauth",
    "login_required", "current_user", "isauthenticated", "requireauth",
)
_VALIDATION_KEYWORDS = (
    "basemodel", "serializer", "schema", "validate", "marshmallow", "zod",
    "joi", "pydantic", "class-validator", "isstring", "isnumber", "isemail",
    "isnotempty",
)

_WORD_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_LAYER_SUFFIX_WORDS = {
    "router", "routers", "route", "routes", "routing",
    "controller", "controllers",
    "service", "services",
    "schema", "schemas",
    "serializer", "serializers",
    "dto", "dtos",
    "model", "models", "entity", "entities",
    "middleware",
    "spec", "specs", "test", "tests",
    "view", "views", "viewset", "viewsets",
    "module", "modules",
}


@dataclass
class IndexedUnit:
    path: Path
    layer: str
    language: str
    symbols: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    http_methods: List[str] = field(default_factory=list)
    route_paths: List[str] = field(default_factory=list)
    entity_terms: List[str] = field(default_factory=list)
    auth_indicators: List[str] = field(default_factory=list)
    validation_indicators: List[str] = field(default_factory=list)
    is_test: bool = False
    snippet: str = ""


@dataclass
class RepositoryIndex:
    units: List[IndexedUnit] = field(default_factory=list)
    framework: str = "unknown"

    def __len__(self) -> int:
        return len(self.units)

    def __iter__(self):
        return iter(self.units)

    def by_layer(self, layer: str) -> List[IndexedUnit]:
        return [unit for unit in self.units if unit.layer == layer]

    def by_language(self, language: str) -> List[IndexedUnit]:
        return [unit for unit in self.units if unit.language == language]

    def tests(self) -> List[IndexedUnit]:
        return [unit for unit in self.units if unit.is_test]

    def with_http_method(self, method: str) -> List[IndexedUnit]:
        method = method.upper()
        return [unit for unit in self.units if method in unit.http_methods]

    def with_entity_term(self, term: str) -> List[IndexedUnit]:
        term = term.lower()
        return [unit for unit in self.units if term in unit.entity_terms]

    def find_by_path(self, path: Union[str, Path]) -> Optional[IndexedUnit]:
        target = str(path).replace("\\", "/")
        for unit in self.units:
            if str(unit.path).replace("\\", "/") == target:
                return unit
        return None


def build_repository_index(
    scan: ScanResult,
    genome: Optional[APIGenome] = None,
) -> RepositoryIndex:
    """
    Build a deterministic, in-memory index of source-code units from an
    already-computed ScanResult.

    Layer assignment is taken directly from ScanResult bucket membership
    (routes/controllers/services/models/schemas/middleware/tests) rather than
    re-classified from scratch. Extraction is regex-based and local: no
    network calls, no embeddings, no persistence to disk.
    """
    units: List[IndexedUnit] = []
    seen_paths = set()

    for bucket_name, layer in _LAYER_BY_BUCKET:
        for path in getattr(scan, bucket_name):
            key = str(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)

            unit = _index_file(path, layer, scan.project_path)
            if unit is not None:
                units.append(unit)

    units.sort(key=lambda unit: (unit.layer, str(unit.path)))

    framework = genome.framework if genome is not None else "unknown"
    return RepositoryIndex(units=units, framework=framework)


def _index_file(path: Path, layer: str, project_path: Path) -> Optional[IndexedUnit]:
    suffix = path.suffix.lower()
    if suffix not in _RECOGNIZED_SUFFIXES:
        return None

    try:
        if not path.is_file():
            return None
        if path.stat().st_size > _MAX_SOURCE_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    language = _LANGUAGE_BY_SUFFIX[suffix]

    try:
        rel_path = path.relative_to(project_path)
    except ValueError:
        rel_path = path

    methods, route_paths = _extract_routes(text)

    return IndexedUnit(
        path=rel_path,
        layer=layer,
        language=language,
        symbols=_extract_symbols(text),
        imports=_extract_imports(text),
        http_methods=methods,
        route_paths=route_paths,
        entity_terms=_extract_entity_terms(rel_path),
        auth_indicators=_match_keywords(text, _AUTH_KEYWORDS),
        validation_indicators=_match_keywords(text, _VALIDATION_KEYWORDS),
        is_test=(layer == "test"),
        snippet=_snippet(text),
    )


def _snippet(text: str) -> str:
    if len(text) <= _MAX_SNIPPET_CHARS:
        return text
    return text[:_MAX_SNIPPET_CHARS] + "..."


def _extract_symbols(text: str) -> List[str]:
    symbols: List[str] = []
    seen = set()

    for pattern in (_CLASS_RE, _PY_DEF_RE, _FUNCTION_RE):
        for match in pattern.finditer(text):
            name = match.group(1)
            if name and name not in seen:
                seen.add(name)
                symbols.append(name)

    for match in _METHOD_RE.finditer(text):
        name = match.group(1)
        if name and name not in _METHOD_KEYWORD_EXCLUSIONS and name not in seen:
            seen.add(name)
            symbols.append(name)

    for match in _DECORATOR_RE.finditer(text):
        name = "@" + match.group(1)
        if name not in seen:
            seen.add(name)
            symbols.append(name)

    return symbols


def _extract_imports(text: str) -> List[str]:
    imports: List[str] = []
    seen = set()

    for match in _PY_IMPORT_RE.finditer(text):
        module = match.group(1) or match.group(2)
        if module and module not in seen:
            seen.add(module)
            imports.append(module)

    for match in _JS_IMPORT_RE.finditer(text):
        module = match.group(1) or match.group(2)
        if module and module not in seen:
            seen.add(module)
            imports.append(module)

    return imports


def _extract_routes(text: str) -> Tuple[List[str], List[str]]:
    pairs: List[Tuple[str, Optional[str]]] = []

    for match in _DECORATOR_METHOD_RE.finditer(text):
        pairs.append((match.group(1).upper(), match.group(2) or None))

    for match in _CALL_METHOD_RE.finditer(text):
        pairs.append((match.group(1).upper(), match.group(2)))

    for match in _FLASK_ROUTE_RE.finditer(text):
        path = match.group(1)
        for word in re.findall(r"[A-Za-z]+", match.group(2)):
            pairs.append((word.upper(), path))

    for match in _DRF_METHOD_DEF_RE.finditer(text):
        pairs.append((match.group(1).upper(), None))

    methods: List[str] = []
    paths: List[str] = []
    seen_methods = set()
    seen_paths = set()

    for method, path in pairs:
        if method not in seen_methods:
            seen_methods.add(method)
            methods.append(method)
        if path and path not in seen_paths:
            seen_paths.add(path)
            paths.append(path)

    return methods, paths


def _extract_entity_terms(rel_path: Path) -> List[str]:
    # Filename alone is enough for conventions like refund_router.py, but
    # frameworks that group per-resource files under a resource-named
    # directory with otherwise-identical filenames (e.g. Django DRF's
    # invoices/views.py vs shipments/views.py) carry the resource identity
    # in the directory, not the filename -- so both are considered. Layer
    # words (routers/, services/, middleware/, ...) contribute nothing
    # either way, since they're filtered below.
    candidates: List[str] = []
    parent_name = rel_path.parent.name
    if parent_name not in ("", "."):
        candidates.append(parent_name)
    candidates.append(rel_path.stem)

    raw_words: List[str] = []
    for candidate in candidates:
        for chunk in _WORD_SPLIT_RE.split(candidate):
            if not chunk:
                continue
            for sub in _CAMEL_SPLIT_RE.split(chunk):
                if sub:
                    raw_words.append(sub.lower())

    terms: List[str] = []
    seen = set()
    for word in raw_words:
        if word in _LAYER_SUFFIX_WORDS or word in seen:
            continue
        seen.add(word)
        terms.append(word)

    return terms


def _match_keywords(text: str, keywords: Tuple[str, ...]) -> List[str]:
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword in lowered]
