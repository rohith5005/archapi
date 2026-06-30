from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from archapi.types import APIPlan, GeneratedFile


class LLMResponseParser:
    """Parses LLM JSON into ArchAPI plan and generated files."""

    def parse_generation_response(
        self,
        request: str,
        raw_text: str,
    ) -> Tuple[APIPlan, List[GeneratedFile]]:
        data = self._load_json(raw_text)

        plan_data = data.get("plan")
        files_data = data.get("files")

        if not isinstance(plan_data, dict):
            raise ValueError("LLM response must contain a plan object.")

        if not isinstance(files_data, list) or not files_data:
            raise ValueError("LLM response must contain a non-empty files list.")

        metadata = plan_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        metadata.setdefault("planner", "llm-openai-v0.1")

        plan = APIPlan(
            request=str(plan_data.get("request") or request),
            method=str(plan_data.get("method") or "GET").upper(),
            path=str(plan_data.get("path") or "/resources/{id}"),
            entities=[str(item) for item in plan_data.get("entities", ["Resource"])],
            layers=[str(item) for item in plan_data.get("layers", [])],
            generation_allowed=bool(plan_data.get("generation_allowed", True)),
            reason=plan_data.get("reason"),
            metadata=metadata,
        )

        generated_files: List[GeneratedFile] = []

        for item in files_data:
            if not isinstance(item, dict):
                continue

            path = Path(str(item.get("path") or ""))
            content = str(item.get("content") or "")

            if not str(path):
                raise ValueError("Generated file path is missing.")
            if path.is_absolute():
                raise ValueError(f"Generated path must be relative: {path}")
            if ".." in path.parts:
                raise ValueError(f"Generated path must not contain '..': {path}")
            if not content.strip():
                raise ValueError(f"Generated file content is empty: {path}")

            generated_files.append(
                GeneratedFile(
                    path=path,
                    content=content,
                    action=str(item.get("action") or "create"),
                )
            )

        if not generated_files:
            raise ValueError("LLM response did not include valid generated files.")

        return plan, generated_files

    def _load_json(self, raw_text: str) -> Dict[str, Any]:
        text = raw_text.strip()

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(text[start : end + 1])

# Backward-compatible name used by core.py and tests.
class ResponseParser(LLMResponseParser):
    def parse(self, raw_text, request=""):
        return self.parse_generation_response(
            request=request,
            raw_text=raw_text,
        )

# Compatibility wrapper used by existing core.py and tests.
class ResponseParser(LLMResponseParser):
    def parse(self, raw_text, request=""):
        data = self._load_json(raw_text)

        # New expected shape:
        # {"plan": {...}, "files": [...]}
        if isinstance(data.get("plan"), dict):
            return self.parse_generation_response(
                request=request,
                raw_text=raw_text,
            )

        # Legacy/simple test shape:
        # {"method": "...", "path": "...", "files": [...]}
        files_data = data.get("files", [])
        if not isinstance(files_data, list):
            files_data = []

        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        metadata.setdefault("planner", "llm-openai-v0.1")
        metadata.setdefault("response_status", data.get("response_status", 200))

        plan = APIPlan(
            request=str(data.get("request") or request),
            method=str(data.get("method") or "GET").upper(),
            path=str(data.get("path") or "/resources/{id}"),
            entities=[str(item) for item in data.get("entities", ["Resource"])],
            layers=[str(item) for item in data.get("layers", [])],
            generation_allowed=bool(data.get("generation_allowed", True)),
            reason=data.get("reason"),
            metadata=metadata,
        )

        generated_files = []

        for item in files_data:
            if not isinstance(item, dict):
                continue

            path = Path(str(item.get("path") or ""))
            content = str(item.get("content") or "")

            if not str(path):
                raise ValueError("Generated file path is missing.")
            if path.is_absolute():
                raise ValueError(f"Generated path must be relative: {path}")
            if ".." in path.parts:
                raise ValueError(f"Generated path must not contain '..': {path}")
            if not content.strip():
                raise ValueError(f"Generated file content is empty: {path}")

            generated_files.append(
                GeneratedFile(
                    path=path,
                    content=content,
                    action=str(item.get("action") or "create"),
                )
            )

        if not generated_files:
            raise ValueError("LLM response did not include valid generated files.")

        return plan, generated_files
