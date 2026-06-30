from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

from archapi.types import APIGenome, ScanResult


# Maximum characters to include from any single example file
_MAX_FILE_SNIPPET = 1500

# Maximum total prompt size (rough guard — real token counting not done here)
_MAX_PROMPT_CHARS = 14_000


class PromptBuilder:
    """
    Builds an architecture-aware LLM prompt that includes:

    - The detected framework and genome (naming / style conventions)
    - Relevant code snippets from the scanned project
    - The user's natural-language API request
    - A strict JSON output schema instruction
    """

    def build(
        self,
        request: str,
        genome: APIGenome,
        scan: Optional[ScanResult] = None,
    ) -> str:
        sections: list[str] = []

        sections.append(self._header())
        sections.append(self._genome_section(genome))

        if scan is not None:
            sections.append(self._project_context_section(scan, genome))

        sections.append(self._request_section(request))
        sections.append(self._output_schema_section(genome))

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

    def _genome_section(self, genome: APIGenome) -> str:
        lines = [
            "## Detected Project Architecture (Genome)",
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

    def _project_context_section(self, scan: ScanResult, genome: APIGenome) -> str:
        """Include the most relevant existing code snippets as architecture examples."""
        snippets: list[str] = []
        budget = _MAX_PROMPT_CHARS // 2  # dedicate half the budget to examples

        # Priority order: routes > services > schemas > tests > controllers
        priority_lists = [
            ("Route example", scan.routes),
            ("Service example", scan.services),
            ("Schema example", scan.schemas),
            ("Test example", scan.tests),
            ("Controller example", scan.controllers),
            ("Middleware example", scan.middleware),
        ]

        for label, paths in priority_lists:
            if not paths or budget <= 0:
                break
            path = paths[0]
            snippet = self._read_snippet(path, genome.framework)
            if snippet:
                block = f"### {label}: `{path.name}`\n```\n{snippet}\n```"
                snippets.append(block)
                budget -= len(block)

        if not snippets:
            return ""

        return "## Existing Project Code Examples\n\n" + "\n\n".join(snippets)

    def _request_section(self, request: str) -> str:
        return f"## API Generation Request\n\n{request}"

    def _output_schema_section(self, genome: APIGenome) -> str:
        return textwrap.dedent(f"""\
            ## Required JSON Output Format

            Respond with ONLY valid JSON — no markdown fences, no commentary.
            The JSON must conform exactly to this schema:

            {{
              "method": "<HTTP method: GET | POST | PUT | PATCH | DELETE>",
              "path": "<REST path, using {{param}} for path parameters>",
              "entities": ["<primary entity name>"],
              "layers": ["<layer names that will be generated>"],
              "files": [
                {{
                  "path": "<relative file path from project root>",
                  "content": "<full file content as a string — escape newlines as \\\\n>"
                }}
              ],
              "reason": "<optional short explanation of decisions made>"
            }}

            Rules:
            - Generate files for framework: {genome.framework}
            - Match the exact naming conventions, imports, and patterns seen above
            - Every generated file must be complete and immediately usable
            - Use {{param}} placeholders in paths (e.g. /users/{{user_id}}/orders)
            - Do not output anything outside the JSON object
        """)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_snippet(self, path: Path, framework: str) -> str:
        """Read up to _MAX_FILE_SNIPPET characters from a source file."""
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return text[:_MAX_FILE_SNIPPET] + ("..." if len(text) > _MAX_FILE_SNIPPET else "")
        except OSError:
            return ""
