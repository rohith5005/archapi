from __future__ import annotations

from pathlib import Path
from typing import List

from archapi.types import GeneratedFile, ValidationReport


class BasicGeneratedCodeValidator:
    """
    Framework-independent validation for generated file objects.
    """

    def validate(self, files: List[GeneratedFile]) -> ValidationReport:
        errors: List[str] = []
        warnings: List[str] = []

        if not files:
            errors.append("No generated files were provided.")

        seen = set()

        for generated in files:
            if not generated.content.strip():
                errors.append(f"Generated file is empty: {generated.path}")

            if str(generated.path) in seen:
                errors.append(f"Duplicate generated path: {generated.path}")

            seen.add(str(generated.path))

            if Path(generated.path).is_absolute():
                errors.append(f"Generated path must be relative, got absolute path: {generated.path}")

            if ".." in Path(generated.path).parts:
                errors.append(f"Generated path must not contain '..': {generated.path}")

        return ValidationReport(success=len(errors) == 0, errors=errors, warnings=warnings)
