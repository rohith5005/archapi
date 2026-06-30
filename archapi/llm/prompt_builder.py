from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from archapi.types import APIGenome


class LLMPromptBuilder:
    """Builds architecture-aware prompts for LLM API generation."""

    def __init__(self, max_files: int = 10, max_chars_per_file: int = 2500) -> None:
        self.max_files = max_files
        self.max_chars_per_file = max_chars_per_file

    def build_generation_prompt(
        self,
        request: str,
        genome: APIGenome,
        maps: Dict[str, Any],
        project_path: Path,
    ) -> str:
        architecture = {
            "framework": genome.framework,
            "route_style": genome.route_style,
            "controller_style": genome.controller_style,
            "service_style": genome.service_style,
            "model_style": genome.model_style,
            "schema_style": genome.schema_style,
            "auth_style": genome.auth_style,
            "error_style": genome.error_style,
            "test_style": genome.test_style,
            "confidence": genome.confidence,
            "metadata": genome.metadata,
        }

        file_context = self._collect_file_context(maps, project_path)

        required_json = {
            "plan": {
                "request": request,
                "method": "GET|POST|PUT|PATCH|DELETE",
                "path": "/resources/{id}",
                "entities": ["Resource"],
                "layers": ["route", "controller", "service", "schema", "test"],
                "generation_allowed": True,
                "reason": None,
                "metadata": {
                    "planner": "llm-openai-v0.1",
                    "resource": "Resource",
                    "action": "custom",
                    "response_status": 200,
                },
            },
            "files": [
                {
                    "path": "relative/path/to/generated_file",
                    "content": "complete file content",
                }
            ],
        }

        return f"""
Generate REST API code for ArchAPI.

User request:
{request}

Detected project architecture:
{json.dumps(architecture, indent=2)}

Relevant existing files:
{json.dumps(file_context, indent=2)}

Rules:
1. Return only valid JSON.
2. Do not use markdown fences.
3. Generate complete file contents.
4. Use relative paths only.
5. Match the detected framework and existing project style.
6. Do not create .env files, private keys, cache files, .git files, dependency folders, or secrets.
7. Keep unknown business logic as safe TODO placeholders.
8. Express TypeScript should normally include route, controller, service, schema, and test.
9. FastAPI should normally include router, service, schema, and test.

Required JSON shape:
{json.dumps(required_json, indent=2)}
""".strip()

    def _collect_file_context(
        self,
        maps: Dict[str, Any],
        project_path: Path,
    ) -> List[Dict[str, str]]:
        file_paths: List[Path] = []

        for key in [
            "route_map",
            "controller_map",
            "service_map",
            "schema_map",
            "model_map",
            "middleware_map",
            "test_map",
        ]:
            value = maps.get(key, {})
            if isinstance(value, dict):
                for candidate in value.values():
                    file_paths.append(Path(candidate))

        context: List[Dict[str, str]] = []
        seen = set()

        for path in file_paths:
            resolved = path.resolve()

            if resolved in seen:
                continue

            if not resolved.exists() or not resolved.is_file():
                continue

            seen.add(resolved)

            try:
                rel = resolved.relative_to(project_path)
            except ValueError:
                rel = resolved.name

            text = resolved.read_text(encoding="utf-8", errors="ignore")
            if len(text) > self.max_chars_per_file:
                text = text[: self.max_chars_per_file] + "\n... truncated ..."

            context.append({"path": str(rel), "content": text})

            if len(context) >= self.max_files:
                break

        return context

# Backward-compatible name used by core.py and tests.
class PromptBuilder(LLMPromptBuilder):
    def build(self, request, genome, maps, project_path):
        return self.build_generation_prompt(
            request=request,
            genome=genome,
            maps=maps,
            project_path=project_path,
        )

# Compatibility wrapper used by existing core.py and tests.
class PromptBuilder(LLMPromptBuilder):
    def build(self, request, genome, scan_or_maps=None, project_path=None):
        from pathlib import Path

        maps = {}

        if scan_or_maps is not None:
            if isinstance(scan_or_maps, dict):
                maps = scan_or_maps
            else:
                # Convert ScanResult-style object into the map shape expected by LLMPromptBuilder.
                maps = {
                    "route_map": {
                        str(i): str(path)
                        for i, path in enumerate(getattr(scan_or_maps, "routes", []) or [])
                    },
                    "controller_map": {
                        str(i): str(path)
                        for i, path in enumerate(getattr(scan_or_maps, "controllers", []) or [])
                    },
                    "service_map": {
                        str(i): str(path)
                        for i, path in enumerate(getattr(scan_or_maps, "services", []) or [])
                    },
                    "schema_map": {
                        str(i): str(path)
                        for i, path in enumerate(getattr(scan_or_maps, "schemas", []) or [])
                    },
                    "model_map": {
                        str(i): str(path)
                        for i, path in enumerate(getattr(scan_or_maps, "models", []) or [])
                    },
                    "middleware_map": {
                        str(i): str(path)
                        for i, path in enumerate(getattr(scan_or_maps, "middleware", []) or [])
                    },
                    "test_map": {
                        str(i): str(path)
                        for i, path in enumerate(getattr(scan_or_maps, "tests", []) or [])
                    },
                }

                if project_path is None:
                    project_path = getattr(scan_or_maps, "project_path", None)

        if project_path is None:
            project_path = Path(".")

        return self.build_generation_prompt(
            request=request,
            genome=genome,
            maps=maps,
            project_path=Path(project_path),
        )
