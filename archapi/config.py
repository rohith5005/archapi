"""
Phase 8C: central ArchAPI configuration.

Before this module, configuration was scattered: LLM settings lived as
individual ArchAPI() constructor kwargs, retrieval budgets lived only
inside ContextBudget/DEFAULT_BUDGET in context_retriever.py with no way to
override them via ArchAPI at all, and there was no project config file or
environment-variable support anywhere.

Resolution precedence (highest to lowest):

    explicit Python/CLI option
            > project config file (archapi.toml)
            > environment variable
            > built-in default

Credentials are never part of this module. API keys are resolved only from
OPENAI_API_KEY (or an explicit constructor argument directly to a provider)
-- never from archapi.toml, never from an environment variable this module
reads into ArchAPIConfig, and never serialized by to_dict().
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional, Union

_CONFIG_FILENAME = "archapi.toml"

KNOWN_LLM_PROVIDERS = {"openai"}

# Defense in depth: refuse to load a config source whose keys look like
# they're trying to carry a credential, wherever that source came from.
_SECRET_LIKE_KEY_SUBSTRINGS = ("key", "secret", "token", "password", "credential")

_BOOL_FIELDS = {"use_llm", "strict_validation"}
_INT_FIELDS = {
    "context_max_chars", "routes_limit", "controllers_limit", "services_limit",
    "schemas_limit", "models_limit", "tests_limit", "auth_patterns_limit",
    "validation_patterns_limit",
}

_ENV_VAR_MAP = {
    "use_llm": "ARCHAPI_USE_LLM",
    "llm_provider": "ARCHAPI_LLM_PROVIDER",
    "llm_model": "ARCHAPI_LLM_MODEL",
    "context_max_chars": "ARCHAPI_CONTEXT_MAX_CHARS",
    "routes_limit": "ARCHAPI_ROUTES_LIMIT",
    "controllers_limit": "ARCHAPI_CONTROLLERS_LIMIT",
    "services_limit": "ARCHAPI_SERVICES_LIMIT",
    "schemas_limit": "ARCHAPI_SCHEMAS_LIMIT",
    "models_limit": "ARCHAPI_MODELS_LIMIT",
    "tests_limit": "ARCHAPI_TESTS_LIMIT",
    "auth_patterns_limit": "ARCHAPI_AUTH_PATTERNS_LIMIT",
    "validation_patterns_limit": "ARCHAPI_VALIDATION_PATTERNS_LIMIT",
    "strict_validation": "ARCHAPI_STRICT_VALIDATION",
}


class ArchAPIConfigError(ValueError):
    """Invalid or unsafe configuration: bad type, unknown provider, a
    config source that looks like it's carrying a credential, or malformed
    TOML. Always raised instead of letting a bad value propagate into a
    silent misconfiguration or a raw parser traceback."""


@dataclass
class ArchAPIConfig:
    use_llm: bool = False
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"

    # Retrieval budget (Phase 7D's ContextBudget) -- previously only
    # settable by constructing ContextRetriever(budget=...) directly, with
    # no path from ArchAPI/CLI at all.
    context_max_chars: int = 12_000
    routes_limit: int = 2
    controllers_limit: int = 2
    services_limit: int = 2
    schemas_limit: int = 2
    models_limit: int = 1
    tests_limit: int = 2
    auth_patterns_limit: int = 1
    validation_patterns_limit: int = 1

    # Escalates non-fatal validation warnings (e.g. the Phase 8A
    # naming-consistency warning) into blocking errors. Defaults to False
    # to preserve existing behavior exactly -- this is an opt-in *extra*
    # caution, never a way to loosen PolicyGate or framework-validation
    # errors, which always block regardless of this flag.
    strict_validation: bool = False

    def __post_init__(self) -> None:
        if self.llm_provider not in KNOWN_LLM_PROVIDERS:
            raise ArchAPIConfigError(
                f"Unknown llm_provider: {self.llm_provider!r}. "
                f"Supported: {sorted(KNOWN_LLM_PROVIDERS)}"
            )

        if not isinstance(self.use_llm, bool):
            raise ArchAPIConfigError(f"use_llm must be a boolean, got {self.use_llm!r}")
        if not isinstance(self.strict_validation, bool):
            raise ArchAPIConfigError(f"strict_validation must be a boolean, got {self.strict_validation!r}")
        if not isinstance(self.llm_model, str) or not self.llm_model.strip():
            raise ArchAPIConfigError(f"llm_model must be a non-empty string, got {self.llm_model!r}")

        for name in _INT_FIELDS:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ArchAPIConfigError(f"{name} must be a non-negative integer, got {value!r}")

    def to_context_budget(self):
        # Local import: avoids a config.py -> indexing import at module
        # load time for callers that never touch retrieval.
        from archapi.indexing.context_retriever import ContextBudget

        return ContextBudget(
            routes=self.routes_limit,
            controllers=self.controllers_limit,
            services=self.services_limit,
            schemas=self.schemas_limit,
            models=self.models_limit,
            tests=self.tests_limit,
            auth_patterns=self.auth_patterns_limit,
            validation_patterns=self.validation_patterns_limit,
            global_char_budget=self.context_max_chars,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Safe to serialize/log/print as JSON: this dataclass has no
        credential field at all."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _parse_bool(raw: str, source: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ArchAPIConfigError(f"Invalid boolean value in {source}: {raw!r}")


def _parse_int(raw: str, source: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ArchAPIConfigError(f"Invalid integer value in {source}: {raw!r}") from None


def _load_toml_dict(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # optional backport, not a hard dependency
        except ImportError:
            import sys
            print(
                f"warning: {path} exists but no TOML parser is available "
                "(tomllib requires Python 3.11+; install 'tomli' for older "
                "versions) -- ignoring project config file.",
                file=sys.stderr,
            )
            return {}

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:  # tomllib.TOMLDecodeError, OSError, ...
        raise ArchAPIConfigError(f"Could not parse {path}: {exc}") from exc

    return data.get("archapi", {})


def _reject_secret_like_keys(raw: Dict[str, Any], source: str) -> None:
    def _walk(node: Dict[str, Any], path: str) -> None:
        for key, value in node.items():
            key_path = f"{path}.{key}" if path else key
            if any(bad in key.lower() for bad in _SECRET_LIKE_KEY_SUBSTRINGS):
                raise ArchAPIConfigError(
                    f"Refusing to load {source}: key {key_path!r} looks like it may hold a "
                    "credential. API keys must come from environment variables only "
                    "(e.g. OPENAI_API_KEY), never from configuration."
                )
            if isinstance(value, dict):
                _walk(value, key_path)

    _walk(raw, "")


def _flatten_toml_section(raw: Dict[str, Any]) -> Dict[str, Any]:
    """[archapi] / [archapi.llm] / [archapi.retrieval] -> ArchAPIConfig's
    flat field names."""
    flat: Dict[str, Any] = {}

    for key in ("use_llm", "strict_validation"):
        if key in raw:
            flat[key] = raw[key]

    llm = raw.get("llm", {})
    if isinstance(llm, dict):
        if "provider" in llm:
            flat["llm_provider"] = llm["provider"]
        if "model" in llm:
            flat["llm_model"] = llm["model"]

    retrieval = raw.get("retrieval", {})
    retrieval_key_map = {
        "max_chars": "context_max_chars",
        "routes": "routes_limit",
        "controllers": "controllers_limit",
        "services": "services_limit",
        "schemas": "schemas_limit",
        "models": "models_limit",
        "tests": "tests_limit",
        "auth_patterns": "auth_patterns_limit",
        "validation_patterns": "validation_patterns_limit",
    }
    if isinstance(retrieval, dict):
        for toml_key, field_name in retrieval_key_map.items():
            if toml_key in retrieval:
                flat[field_name] = retrieval[toml_key]

    return flat


def _values_from_environment() -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for field_name, env_var in _ENV_VAR_MAP.items():
        raw = os.environ.get(env_var)
        if raw is None:
            continue
        if field_name in _BOOL_FIELDS:
            values[field_name] = _parse_bool(raw, env_var)
        elif field_name in _INT_FIELDS:
            values[field_name] = _parse_int(raw, env_var)
        else:
            values[field_name] = raw
    return values


def load_config(
    project_path: Union[str, Path] = ".",
    overrides: Optional[Dict[str, Any]] = None,
) -> ArchAPIConfig:
    """
    Resolve an ArchAPIConfig for `project_path` with precedence:
    explicit `overrides` > project archapi.toml (if present) >
    environment variables > built-in defaults.

    Raises ArchAPIConfigError for malformed TOML, an unknown provider, a
    wrong-typed value, or any config source that looks like it's trying to
    carry a credential -- never lets a bad value through silently or with
    a raw parser traceback.
    """
    values: Dict[str, Any] = _values_from_environment()

    config_path = Path(project_path) / _CONFIG_FILENAME
    if config_path.exists():
        raw_toml = _load_toml_dict(config_path)
        _reject_secret_like_keys(raw_toml, str(config_path))
        values.update(_flatten_toml_section(raw_toml))

    if overrides:
        _reject_secret_like_keys(overrides, "explicit configuration overrides")
        values.update({k: v for k, v in overrides.items() if v is not None})

    try:
        return ArchAPIConfig(**values)
    except TypeError as exc:
        raise ArchAPIConfigError(f"Invalid configuration key: {exc}") from exc
