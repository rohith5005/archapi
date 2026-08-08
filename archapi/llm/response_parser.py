from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from archapi.llm.errors import LLMParseError
from archapi.types import APIPlan, GeneratedFile


_REQUIRED_TOP_LEVEL = {"method", "path", "entities", "files"}
_REQUIRED_FILE_KEYS = {"path", "content"}

_VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


class ResponseParser:
    """
    Parses the raw JSON string returned by an LLM provider into
    an ``APIPlan`` + ``List[GeneratedFile]`` pair.

    The parser is intentionally lenient about extra fields but strict
    about required fields and basic data types.
    """

    def parse(self, raw: str) -> Tuple[APIPlan, List[GeneratedFile]]:
        """
        Parse *raw* LLM output into an (APIPlan, files) tuple.

        :param raw: Raw string from the LLM (must be valid JSON).
        :returns: ``(APIPlan, List[GeneratedFile])``
        :raises LLMParseError: If *raw* is not valid JSON or is missing required fields.
        """
        data = self._load_json(raw)
        self._validate_top_level(data)

        plan = self._build_plan(data)
        files = self._build_files(data.get("files", []))

        return plan, files

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_json(self, raw: str) -> Dict[str, Any]:
        """Attempt to parse *raw* as JSON, stripping markdown fences if present."""
        text = raw.strip()

        # Strip ```json ... ``` or ``` ... ``` fences that the model may add
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last fence lines
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMParseError(
                f"LLM response is not valid JSON: {exc}\n\nRaw response:\n{raw[:500]}"
            ) from exc

    def _validate_top_level(self, data: Dict[str, Any]) -> None:
        missing = _REQUIRED_TOP_LEVEL - data.keys()
        if missing:
            raise LLMParseError(
                f"LLM response missing required fields: {sorted(missing)}"
            )

        method = str(data.get("method", "")).upper()
        if method not in _VALID_METHODS:
            raise LLMParseError(
                f"LLM returned invalid HTTP method: '{method}'. "
                f"Expected one of {sorted(_VALID_METHODS)}."
            )

        if not isinstance(data.get("files"), list):
            raise LLMParseError("LLM response 'files' must be a list.")

        if not data["files"]:
            raise LLMParseError("LLM response 'files' list is empty — no files were generated.")

    def _build_plan(self, data: Dict[str, Any]) -> APIPlan:
        method = str(data["method"]).upper()
        path = str(data["path"])
        entities = list(data.get("entities", []))
        layers = list(data.get("layers", []))
        reason = data.get("reason")

        # Normalise entities to non-empty list
        if not entities:
            # Derive from path: last non-parameterised segment
            parts = [p for p in path.split("/") if p and not p.startswith("{")]
            entities = [parts[-1].rstrip("s")] if parts else ["resource"]

        return APIPlan(
            request=data.get("request", ""),
            method=method,
            path=path,
            entities=entities,
            layers=layers,
            generation_allowed=True,
            reason=reason,
            metadata={"source": "llm", **{k: v for k, v in data.items()
                                           if k not in ("method", "path", "entities", "layers",
                                                        "files", "reason", "request")}},
        )

    def _build_files(self, raw_files: list) -> List[GeneratedFile]:
        files: List[GeneratedFile] = []
        for idx, item in enumerate(raw_files):
            if not isinstance(item, dict):
                raise LLMParseError(f"LLM 'files[{idx}]' must be an object, got {type(item).__name__}.")

            missing = _REQUIRED_FILE_KEYS - item.keys()
            if missing:
                raise LLMParseError(
                    f"LLM 'files[{idx}]' is missing required keys: {sorted(missing)}."
                )

            file_path = Path(str(item["path"]))
            content = str(item["content"])

            # Unescape \\n sequences that some models emit
            content = content.replace("\\n", "\n").replace("\\t", "\t")

            action = str(item.get("action", "create"))
            files.append(GeneratedFile(path=file_path, content=content, action=action))

        return files
