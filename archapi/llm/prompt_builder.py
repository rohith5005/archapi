from __future__ import annotations

import textwrap
from typing import Dict, List, Optional

from archapi.indexing.context_retriever import RetrievedContext
from archapi.types import APIGenome, APIPlan


# Maximum total prompt size (rough guard -- real token counting not done here)
_MAX_PROMPT_CHARS = 14_000

# Per-framework file-naming conventions that ArchAPI's own post-generation
# validator enforces -- telling the model up front avoids generating
# architecturally-correct code that still fails the structural check.
_REQUIRED_LAYER_HINTS = {
    "fastapi": (
        "route files must end in `_router.py`, services in `_service.py`, "
        "schemas in `_schema.py`, and include a test file under `tests/` starting with `test_`"
    ),
    "flask": (
        "route files must end in `_routes.py`, services in `_service.py`, "
        "schemas in `_schema.py`, and include a test file under `tests/` starting with `test_`"
    ),
    "django-drf": (
        "include files named exactly `views.py`, `serializers.py`, and `urls.py`, "
        "plus a test file with `test_` in its name"
    ),
    "nestjs": (
        "include files ending in `.controller.ts`, `.service.ts`, `.module.ts`, and `.dto.ts`, "
        "plus a `.spec.ts` test file"
    ),
    "express-typescript": (
        "include files under paths containing `routes`, `controllers`, `services`, `schemas`, and `tests`"
    ),
}

_LABELED_CATEGORIES = (
    ("ROUTE", "routes"),
    ("CONTROLLER", "controllers"),
    ("SERVICE", "services"),
    ("SCHEMA", "schemas"),
    ("MODEL", "models"),
    ("AUTHENTICATION PATTERN", "auth_patterns"),
    ("VALIDATION PATTERN", "validation_patterns"),
    ("TEST", "tests"),
)


class PromptBuilder:
    """
    Builds an architecture-aware LLM prompt from:

    - The detected framework and genome (naming / style conventions)
    - The user's natural-language API request
    - An (optional) deterministically-inferred implementation plan
    - An (optional) pre-retrieved, budgeted RetrievedContext (Phase 7D) of
      the repository examples most relevant to this specific request

    This class does not select which repository files are relevant --
    that decision belongs to ContextRetriever. If no retrieved_context is
    supplied, the prompt is built from architecture/genome/request
    information alone; it does not fall back to picking arbitrary project
    files itself.
    """

    def build(
        self,
        request: str,
        genome: APIGenome,
        plan: Optional[APIPlan] = None,
        retrieved_context: Optional[RetrievedContext] = None,
    ) -> str:
        sections: List[str] = []

        sections.append(self._header())
        sections.append(self._architecture_section(genome))
        sections.append(self._request_section(request))

        if plan is not None:
            sections.append(self._plan_section(plan))

        if retrieved_context is not None:
            examples = self._examples_section(retrieved_context)
            if examples:
                sections.append(examples)

        sections.append(self._generation_rules_section(genome))

        prompt = "\n\n".join(s for s in sections if s.strip())

        # Safety: truncate if exceeds guard limit
        if len(prompt) > _MAX_PROMPT_CHARS:
            prompt = prompt[:_MAX_PROMPT_CHARS] + "\n\n[...project context truncated for token limit...]"

        return prompt

    # ------------------------------------------------------------------
    # Private section builders
    # ------------------------------------------------------------------

    def _header(self) -> str:
        return textwrap.dedent("""\
            You are ArchAPI — an expert API engineer that generates production-quality
            REST API code. Your task is to generate new API files that EXACTLY match
            the architecture, naming conventions, folder structure, validation style,
            service pattern, and test style of the existing project shown below.

            Do NOT introduce new patterns or libraries that are not already present in
            the project. Match what exists as closely as possible.
        """)

    def _architecture_section(self, genome: APIGenome) -> str:
        lines = [
            "## PROJECT ARCHITECTURE",
            "",
            f"- Framework       : {genome.framework}",
            f"- Route style     : {genome.route_style}",
            f"- Controller style: {genome.controller_style}",
            f"- Service style   : {genome.service_style}",
            f"- Schema style    : {genome.schema_style}",
            f"- Test style      : {genome.test_style}",
            f"- Auth style      : {genome.auth_style}",
            f"- Confidence      : {genome.confidence}",
        ]

        if genome.metadata:
            lang = genome.metadata.get("language")
            if lang:
                lines.append(f"- Language        : {lang}")

        return "\n".join(lines)

    def _request_section(self, request: str) -> str:
        return f"## USER REQUEST\n\n{request}"

    def _plan_section(self, plan: APIPlan) -> str:
        lines = [
            "## IMPLEMENTATION PLAN",
            "",
            "Inferred from the request above -- refine as needed, but stay consistent with it:",
            "",
            f"- Method   : {plan.method}",
            f"- Path     : {plan.path}",
            f"- Entities : {', '.join(plan.entities) or 'unknown'}",
            f"- Layers   : {', '.join(plan.layers) or 'unknown'}",
        ]
        return "\n".join(lines)

    def _examples_section(self, context: RetrievedContext) -> str:
        blocks: List[str] = []
        seen_paths: Dict[str, str] = {}

        for label, attr in _LABELED_CATEGORIES:
            for item in getattr(context, attr):
                if item.path in seen_paths:
                    blocks.append(
                        f"[{label}] {item.path}\n"
                        f"(same file as the {seen_paths[item.path]} example above -- "
                        "also demonstrates this pattern)"
                    )
                    continue

                seen_paths[item.path] = label
                blocks.append(f"[{label}] {item.path}\n```\n{item.snippet}\n```")

        if not blocks:
            return ""

        intro = textwrap.dedent("""\
            ## RELEVANT EXISTING PROJECT EXAMPLES

            These examples were selected from this repository because they are the
            most relevant to the request above. Imitate their architectural patterns
            -- naming, structure, imports, error handling -- rather than copying their
            literal business logic. Reuse the authentication and validation
            conventions demonstrated here instead of inventing new ones.
        """)

        return intro + "\n" + "\n\n".join(blocks)

    def _generation_rules_section(self, genome: APIGenome) -> str:
        schema = textwrap.dedent("""\
            ## GENERATION RULES

            ## Required JSON Output Format

            Respond with ONLY valid JSON — no markdown fences, no commentary.
            The JSON must conform exactly to this schema:

            {
              "method": "<HTTP method: GET | POST | PUT | PATCH | DELETE>",
              "path": "<REST path, using {param} for path parameters>",
              "entities": ["<primary entity name>"],
              "layers": ["<layer names that will be generated>"],
              "files": [
                {
                  "path": "<relative file path from project root>",
                  "content": "<full file content as a string — escape newlines as \\\\n>"
                }
              ],
              "reason": "<optional short explanation of decisions made>"
            }

            Rules:
        """)

        rules = [
            f"- Generate files for framework: {genome.framework}",
            "- Match the exact naming conventions, imports, and patterns seen above",
            "- Imitate the architectural patterns in the examples above; do not copy "
            "their business logic verbatim",
            "- Reuse the existing authentication and validation conventions shown "
            "above rather than inventing new ones",
            "- Only generate files required by the implementation plan above; do "
            "not add unrequested infrastructure",
            "- Every generated file must be complete and immediately usable",
            "- Use {param} placeholders in paths (e.g. /users/{user_id}/orders)",
            "- Do not create new application entry-point or bootstrap files "
            "(e.g. main.py, app.py, settings.py, wsgi.py, asgi.py, index.ts, server.ts) "
            "— only generate the requested API layer files",
            "- If you generate a new middleware/auth-guard file, include \"middleware\" in \"layers\"",
            "- Do not output anything outside the JSON object",
        ]

        layer_hint = _REQUIRED_LAYER_HINTS.get(genome.framework)
        if layer_hint:
            rules.insert(1, f"- Required file naming for this framework: {layer_hint}")

        return schema + "\n".join(rules) + "\n"
