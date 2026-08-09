from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        scan: Optional[ScanResult] = None,
    ) -> ValidationReport:
        """
        :param scan: The project's ScanResult, when available. Lets a
            validator check generated files against conventions the
            repository itself demonstrates (e.g. an existing project-local
            test-naming style), rather than only a hardcoded framework
            default. Optional and backward compatible -- callers/tests that
            don't have a ScanResult on hand may omit it.
        """
        raise NotImplementedError
