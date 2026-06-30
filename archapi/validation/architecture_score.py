from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from archapi.types import APIGenome, GeneratedFile


@dataclass
class ArchitectureScore:
    score: float
    max_score: float
    percentage: float
    passed: Dict[str, bool] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class ArchitectureConsistencyScorer:
    """
    Scores whether generated API files follow the detected project architecture.

    v0.3 supports Express TypeScript and FastAPI layer conventions.
    """

    def score(self, files: List[GeneratedFile], genome: APIGenome) -> ArchitectureScore:
        generated_paths = [str(file.path).replace("\\", "/") for file in files]
        generated_text = "\n".join(file.content for file in files)

        if genome.framework == "fastapi":
            checks = self._score_fastapi(generated_paths, generated_text, genome)
        else:
            checks = self._score_express(generated_paths, generated_text, genome)

        max_score = float(len(checks))
        raw_score = float(sum(1 for value in checks.values() if value))
        percentage = round((raw_score / max_score) * 100, 2) if max_score else 0.0

        notes = [
            f"Failed architecture check: {name}"
            for name, passed in checks.items()
            if not passed
        ]

        return ArchitectureScore(
            score=raw_score,
            max_score=max_score,
            percentage=percentage,
            passed=checks,
            notes=notes,
        )

    def _score_express(self, paths: List[str], text: str, genome: APIGenome) -> Dict[str, bool]:
        return {
            "has_route_layer": any("/routes/" in p or p.startswith("src/routes/") for p in paths),
            "has_controller_layer": any("/controllers/" in p or p.startswith("src/controllers/") for p in paths),
            "has_service_layer": any("/services/" in p or p.startswith("src/services/") for p in paths),
            "has_schema_layer": any("/schemas/" in p or p.startswith("src/schemas/") for p in paths),
            "has_test_layer": any("/tests/" in p or p.startswith("tests/") for p in paths),
            "matches_express_router": genome.framework != "express-typescript" or "Router" in text,
            "matches_controller_style": genome.controller_style == "unknown" or "Request" in text or "Response" in text,
            "matches_service_style": genome.service_style == "unknown" or "Service" in text or "service" in text,
            "matches_schema_style": genome.schema_style == "unknown" or genome.schema_style not in {"zod", "joi"} or genome.schema_style in text.lower(),
            "matches_test_style": genome.test_style == "unknown" or "describe(" in text or "it(" in text,
        }

    def _score_fastapi(self, paths: List[str], text: str, genome: APIGenome) -> Dict[str, bool]:
        return {
            "has_router_layer": any("/routers/" in p or p.startswith("app/routers/") for p in paths),
            "has_service_layer": any("/services/" in p or p.startswith("app/services/") for p in paths),
            "has_schema_layer": any("/schemas/" in p or p.startswith("app/schemas/") for p in paths),
            "has_test_layer": any("/tests/" in p or p.startswith("tests/") for p in paths),
            "matches_apirouter": "APIRouter" in text,
            "matches_async_endpoint": "async def" in text,
            "matches_pydantic_schema": "BaseModel" in text,
            "matches_service_style": "Service" in text or "_service" in text,
            "matches_test_style": "def test_" in text,
        }
