from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from archapi.types import APIGenome, DetectionResult, ScanResult


IGNORED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    "vendor",
    "target",
    ".archapi",
}


class CacheManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.cache_dir = project_path / ".archapi"

    def ensure_cache_dir(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def save_json(self, name: str, data: Dict[str, Any]) -> Path:
        self.ensure_cache_dir()
        target = self.cache_dir / name
        target.write_text(
            json.dumps(self._json_safe(data), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target

    def load_json(self, name: str) -> Optional[Dict[str, Any]]:
        target = self.cache_dir / name
        if not target.exists():
            return None

        return json.loads(target.read_text(encoding="utf-8"))

    def hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def collect_file_hashes(self) -> Dict[str, str]:
        hashes: Dict[str, str] = {}

        for path in self.project_path.rglob("*"):
            if path.is_dir():
                continue

            if any(part in IGNORED_DIRS for part in path.parts):
                continue

            rel = str(path.relative_to(self.project_path))
            hashes[rel] = self.hash_file(path)

        return hashes

    def changed_files(self) -> List[str]:
        old_hashes = self.load_json("file_hashes.json") or {}
        new_hashes = self.collect_file_hashes()

        changed: List[str] = []

        all_files = set(old_hashes.keys()) | set(new_hashes.keys())

        for file in sorted(all_files):
            if old_hashes.get(file) != new_hashes.get(file):
                changed.append(file)

        return changed

    def save_snapshot(
        self,
        detection: DetectionResult,
        scan: ScanResult,
        maps: Dict[str, Any],
        genome: APIGenome,
    ) -> Dict[str, Path]:
        saved = {}

        saved["file_hashes"] = self.save_json(
            "file_hashes.json",
            self.collect_file_hashes(),
        )

        saved["detection"] = self.save_json(
            "detection.json",
            self._json_safe(detection),
        )

        saved["project_index"] = self.save_json(
            "project_index.json",
            self._json_safe(scan),
        )

        saved["maps"] = self.save_json(
            "maps.json",
            self._json_safe(maps),
        )

        saved["genome"] = self.save_json(
            "genome.json",
            self._json_safe(genome),
        )

        return saved

    def _json_safe(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._json_safe(asdict(value))

        if isinstance(value, Path):
            try:
                return str(value.relative_to(self.project_path))
            except ValueError:
                return str(value)

        if isinstance(value, dict):
            return {
                str(k): self._json_safe(v)
                for k, v in value.items()
            }

        if isinstance(value, list):
            return [self._json_safe(v) for v in value]

        return value
