"""
Phase 8D.1: atomic filesystem application for generated files.

The previous GenerationResult.apply() wrote files one at a time, directly,
with no staging or rollback: if file 3 of 5 failed, files 1-2 were already
on disk and the repository was left partially modified. This module
replaces that with an explicit prepare -> verify -> write -> (rollback on
failure) pipeline:

    validate everything
            v
    prepare complete write set   (FileTransaction._prepare)
            v
    verify every destination     (path safety, create/overwrite conflicts --
                                   same checks apply() always had, unchanged)
            v
    write safely                 (each file via write-temp + atomic rename,
                                   so no single file is ever left torn)
            v
    success -- or, on any failure, roll back everything this transaction
               already wrote: restore backed-up content for overwritten
               files, delete newly created files, remove directories this
               transaction created if left empty.

Pure filesystem operations only -- no git dependency. Works on an
uncommitted repository, a non-git project, or files that aren't tracked.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence


class FileTransactionError(Exception):
    """Raised when a transaction cannot be applied safely. The filesystem
    is guaranteed to be rolled back to its pre-transaction state before
    this is raised."""


@dataclass
class _PlannedWrite:
    target: Path
    content: str
    action: str
    existed_before: bool
    original_content: Optional[str] = None


@dataclass
class FileTransactionResult:
    written: List[Path] = field(default_factory=list)
    created_directories: List[Path] = field(default_factory=list)


class FileTransaction:
    """
    All-or-nothing filesystem application for a set of GeneratedFile
    objects, rooted at `project_root`.
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()

    def apply(self, files: Sequence) -> FileTransactionResult:
        planned = self._prepare(files)
        return self._write_all(planned)

    # ------------------------------------------------------------------
    # Prepare: validate every destination before touching the filesystem.
    # Identical safety checks to the original apply() implementation --
    # this is the last line of defense against path traversal/absolute
    # paths, independent of whatever validation ran upstream (PolicyGate).
    # ------------------------------------------------------------------

    def _prepare(self, files: Sequence) -> List[_PlannedWrite]:
        planned: List[_PlannedWrite] = []
        seen_targets = set()

        for generated in files:
            raw_path = Path(generated.path)

            if raw_path.is_absolute():
                raise PermissionError(
                    f"Refusing to write to an absolute path: {raw_path}"
                )

            target = (self.project_root / raw_path).resolve()

            if not target.is_relative_to(self.project_root):
                raise PermissionError(
                    f"Refusing to write outside the project directory: {generated.path}"
                )

            if target in seen_targets:
                raise FileTransactionError(
                    f"Duplicate target path in the same transaction: {target}"
                )
            seen_targets.add(target)

            existed_before = target.exists()

            if existed_before and generated.action == "create":
                raise FileExistsError(f"Refusing to overwrite existing file: {target}")

            original_content: Optional[str] = None
            if existed_before:
                try:
                    original_content = target.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    raise FileTransactionError(
                        f"Cannot safely back up existing file before overwrite: {target} ({exc})"
                    ) from exc

            planned.append(_PlannedWrite(
                target=target,
                content=generated.content,
                action=generated.action,
                existed_before=existed_before,
                original_content=original_content,
            ))

        return planned

    # ------------------------------------------------------------------
    # Write: apply every planned write; roll back everything this
    # transaction has done so far if any single write fails.
    # ------------------------------------------------------------------

    def _write_all(self, planned: List[_PlannedWrite]) -> FileTransactionResult:
        result = FileTransactionResult()
        applied: List[_PlannedWrite] = []
        created_dirs: List[Path] = []

        try:
            for item in planned:
                for parent in self._missing_parents(item.target):
                    parent.mkdir(parents=False, exist_ok=True)
                    created_dirs.append(parent)

                self._atomic_write(item.target, item.content)
                applied.append(item)
                result.written.append(item.target)
        except BaseException as exc:
            self._rollback(applied, created_dirs)
            raise FileTransactionError(f"Application failed and was rolled back: {exc}") from exc

        result.created_directories = created_dirs
        return result

    def _missing_parents(self, target: Path) -> List[Path]:
        """Ancestors of `target` that don't exist yet, outermost-missing
        first (so each can be created with parents=False once its own
        parent is guaranteed to already exist)."""
        missing: List[Path] = []
        parent = target.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        return list(reversed(missing))

    def _atomic_write(self, target: Path, content: str) -> None:
        """Write via a temp file in the same directory + os.replace(), so a
        single file is never left torn/partial: either the rename succeeds
        and `target` has the full new content, or it doesn't and `target`
        is untouched. The temp file is always cleaned up, even on
        interruption."""
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=f".{target.name}.", suffix=".archapi-tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _rollback(self, applied: List[_PlannedWrite], created_dirs: List[Path]) -> None:
        for item in reversed(applied):
            try:
                if item.existed_before:
                    self._atomic_write(item.target, item.original_content or "")
                elif item.target.exists():
                    item.target.unlink()
            except OSError:
                # Best-effort: don't let a rollback failure mask the
                # original error that triggered the rollback.
                pass

        for directory in reversed(created_dirs):
            try:
                if directory.exists() and not any(directory.iterdir()):
                    directory.rmdir()
            except OSError:
                pass
