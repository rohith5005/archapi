from __future__ import annotations

import json
from pathlib import Path
from typing import List

from archapi.types import DetectionResult


class FrameworkDetector:
    def detect(self, project_path: Path) -> DetectionResult:
        candidates: List[DetectionResult] = []

        package_json = project_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                deps = {}
                deps.update(data.get("dependencies", {}))
                deps.update(data.get("devDependencies", {}))

                if "@nestjs/core" in deps:
                    candidates.append(
                        DetectionResult("nestjs", 0.95, ["package.json contains @nestjs/core"])
                    )

                if "express" in deps:
                    candidates.append(
                        DetectionResult("express-typescript", 0.85, ["package.json contains express"])
                    )
            except Exception:
                candidates.append(
                    DetectionResult("node-unknown", 0.30, ["package.json exists but could not be parsed"])
                )

        if (project_path / "manage.py").exists():
            candidates.append(
                DetectionResult("django-drf", 0.75, ["manage.py detected"])
            )

        py_text = ""
        pyproject = project_path / "pyproject.toml"
        requirements = project_path / "requirements.txt"

        if pyproject.exists():
            py_text += pyproject.read_text(encoding="utf-8", errors="ignore").lower()

        if requirements.exists():
            py_text += requirements.read_text(encoding="utf-8", errors="ignore").lower()

        if "fastapi" in py_text:
            candidates.append(
                DetectionResult("fastapi", 0.90, ["fastapi dependency detected"])
            )

        if "flask" in py_text:
            candidates.append(
                DetectionResult("flask", 0.85, ["flask dependency detected"])
            )

        if (project_path / "pom.xml").exists() or (project_path / "build.gradle").exists():
            candidates.append(
                DetectionResult("spring-boot", 0.70, ["Java build file detected"])
            )

        if list(project_path.glob("*.csproj")):
            candidates.append(
                DetectionResult("dotnet-core", 0.75, [".csproj file detected"])
            )

        if (project_path / "composer.json").exists():
            composer = (project_path / "composer.json").read_text(
                encoding="utf-8",
                errors="ignore",
            ).lower()
            if "laravel" in composer:
                candidates.append(
                    DetectionResult("laravel", 0.90, ["composer.json contains laravel"])
                )

        if (project_path / "Gemfile").exists():
            gemfile = (project_path / "Gemfile").read_text(
                encoding="utf-8",
                errors="ignore",
            ).lower()
            if "rails" in gemfile:
                candidates.append(
                    DetectionResult("rails", 0.90, ["Gemfile contains rails"])
                )

        if (project_path / "go.mod").exists():
            go_mod = (project_path / "go.mod").read_text(
                encoding="utf-8",
                errors="ignore",
            ).lower()

            if "gin-gonic/gin" in go_mod or "gofiber/fiber" in go_mod:
                candidates.append(
                    DetectionResult("go-api", 0.85, ["go.mod contains Gin or Fiber"])
                )
            else:
                candidates.append(
                    DetectionResult("go-api", 0.55, ["go.mod detected"])
                )

        if not candidates:
            return DetectionResult(
                framework="generic",
                confidence=0.10,
                reasons=["No known framework markers detected"],
            )

        return sorted(candidates, key=lambda item: item.confidence, reverse=True)[0]
