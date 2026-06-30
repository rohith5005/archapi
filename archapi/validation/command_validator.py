from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class CommandResult:
    name: str
    command: List[str]
    skipped: bool
    success: bool
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    reason: Optional[str] = None


@dataclass
class CommandValidationReport:
    success: bool
    results: List[CommandResult] = field(default_factory=list)

    @property
    def errors(self) -> List[str]:
        messages: List[str] = []
        for result in self.results:
            if not result.skipped and not result.success:
                messages.append(
                    f"{result.name} failed with exit code {result.returncode}"
                )
        return messages


class CommandValidator:
    """
    Runs project validation commands only when they are available.

    v0.2 supports Node/TypeScript package.json scripts:
    - build
    - test
    - lint
    """

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)

    def validate_node_project(self) -> CommandValidationReport:
        package_json = self.project_path / "package.json"

        if not package_json.exists():
            return CommandValidationReport(
                success=True,
                results=[
                    CommandResult(
                        name="node_project",
                        command=[],
                        skipped=True,
                        success=True,
                        reason="package.json not found",
                    )
                ],
            )

        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception as exc:
            return CommandValidationReport(
                success=False,
                results=[
                    CommandResult(
                        name="package_json_parse",
                        command=[],
                        skipped=False,
                        success=False,
                        reason=f"Failed to parse package.json: {exc}",
                    )
                ],
            )

        scripts: Dict[str, str] = data.get("scripts", {})

        checks = [
            ("build", ["npm", "run", "build"]),
            ("test", ["npm", "test"]),
            ("lint", ["npm", "run", "lint"]),
        ]

        results: List[CommandResult] = []

        for script_name, command in checks:
            if script_name not in scripts:
                results.append(
                    CommandResult(
                        name=script_name,
                        command=command,
                        skipped=True,
                        success=True,
                        reason=f"script '{script_name}' not found in package.json",
                    )
                )
                continue

            results.append(self._run(script_name, command))

        success = all(result.success for result in results)
        return CommandValidationReport(success=success, results=results)

    def _run(self, name: str, command: List[str]) -> CommandResult:
        try:
            completed = subprocess.run(
                command,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            return CommandResult(
                name=name,
                command=command,
                skipped=False,
                success=completed.returncode == 0,
                returncode=completed.returncode,
                stdout=completed.stdout[-4000:],
                stderr=completed.stderr[-4000:],
            )
        except FileNotFoundError:
            return CommandResult(
                name=name,
                command=command,
                skipped=True,
                success=True,
                reason=f"Command not available: {command[0]}",
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                name=name,
                command=command,
                skipped=False,
                success=False,
                reason="Command timed out after 60 seconds",
            )
