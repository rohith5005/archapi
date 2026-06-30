from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from archapi.types import (
    APIPlan,
    APIGenome,
    DetectionResult,
    GeneratedFile,
    ScanResult,
    ValidationReport,
)


class FrameworkAdapter(ABC):
    name: str = "unknown"

    @abstractmethod
    def detect(self, project_path: Path) -> DetectionResult:
        raise NotImplementedError

    @abstractmethod
    def scan(self, project_path: Path) -> ScanResult:
        raise NotImplementedError

    @abstractmethod
    def build_maps(self, scan_result: ScanResult) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def extract_genome(self, maps: Dict[str, Any], scan_result: ScanResult) -> APIGenome:
        raise NotImplementedError

    @abstractmethod
    def plan_api(self, request: str, genome: APIGenome, maps: Dict[str, Any]) -> APIPlan:
        raise NotImplementedError

    @abstractmethod
    def generate_code(
        self,
        plan: APIPlan,
        genome: APIGenome,
        maps: Dict[str, Any],
    ) -> List[GeneratedFile]:
        raise NotImplementedError

    @abstractmethod
    def validate_generated_code(
        self,
        files: List[GeneratedFile],
        plan: APIPlan,
        genome: APIGenome,
    ) -> ValidationReport:
        raise NotImplementedError
