from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from archapi.frameworks.detector import FrameworkDetector
from archapi.frameworks.registry import FrameworkRegistry
from archapi.indexing.cache import CacheManager
from archapi.security.secret_scanner import SecretScanner
from archapi.security.context_redactor import ContextRedactor
from archapi.security.policy_gate import PolicyGate
from archapi.validation.architecture_score import ArchitectureConsistencyScorer
from archapi.validation.command_validator import CommandValidator
from archapi.types import (
    APIGenome,
    APIPlan,
    DetectionResult,
    GeneratedFile,
    GenerationResult,
    ScanResult,
    ValidationReport,
)


class ArchAPI:
    def __init__(
        self,
        project_path: Union[str, Path],
        framework: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
        llm_model: str = "gpt-4o-mini",
        llm_provider=None,
        api_key: Optional[str] = None,
    ):
        self.project_path = Path(project_path).resolve()
        if not self.project_path.exists():
            raise FileNotFoundError(f"Project path does not exist: {self.project_path}")

        self._framework_override = framework
        self._config = config or {}
        self._use_llm = use_llm
        self._llm_model = llm_model
        self._api_key = api_key
        self._detector = FrameworkDetector()
        self._registry = FrameworkRegistry()
        self._cache = CacheManager(self.project_path)
        self._secret_scanner = SecretScanner(self.project_path)
        self._context_redactor = ContextRedactor()
        self._policy_gate = PolicyGate()
        self._architecture_scorer = ArchitectureConsistencyScorer()
        self._command_validator = CommandValidator(self.project_path)

        self._detection: Optional[DetectionResult] = None
        self._scan: Optional[ScanResult] = None
        self._maps: Optional[Dict[str, Any]] = None
        self._genome: Optional[APIGenome] = None

        # Resolve LLM provider (lazy — only initialised when use_llm=True)
        self._llm = llm_provider  # may be None; initialised in _resolve_llm()

    def detect_framework(self) -> DetectionResult:
        if self._framework_override:
            self._detection = DetectionResult(
                framework=self._framework_override,
                confidence=1.0,
                reasons=["Framework explicitly provided"],
            )
            return self._detection

        self._detection = self._detector.detect(self.project_path)
        return self._detection

    def _adapter(self):
        detection = self._detection or self.detect_framework()
        return self._registry.get(detection.framework)

    def _has_config_hints(self) -> bool:
        hint_keys = {
            "route_dir",
            "controller_dir",
            "service_dir",
            "model_dir",
            "schema_dir",
            "middleware_dir",
            "test_dir",
        }
        return any(key in self._config for key in hint_keys)

    def scan(self) -> ScanResult:
        detection = self._detection or self.detect_framework()

        # Strict config mode:
        # If user provides architecture hints, scan ONLY those hinted directories.
        # This prevents accidental scanning of the library repo, sample projects,
        # caches, or unrelated test files.
        if self._has_config_hints():
            self._scan = ScanResult(
                framework=detection.framework,
                project_path=self.project_path,
            )
            self._apply_config_hints_to_scan(self._scan)
            return self._scan

        adapter = self._adapter()
        self._scan = adapter.scan(self.project_path)
        self._scan.framework = detection.framework
        return self._scan

    def _apply_config_hints_to_scan(self, scan: ScanResult) -> None:
        """
        Applies user-provided architecture hints.

        Supported config keys:
        - route_dir
        - controller_dir
        - service_dir
        - model_dir
        - schema_dir
        - middleware_dir
        - test_dir
        """

        hint_map = {
            "route_dir": scan.routes,
            "controller_dir": scan.controllers,
            "service_dir": scan.services,
            "model_dir": scan.models,
            "schema_dir": scan.schemas,
            "middleware_dir": scan.middleware,
            "test_dir": scan.tests,
        }

        ignored_parts = {
            ".git",
            ".venv",
            "node_modules",
            "dist",
            "build",
            "coverage",
            "__pycache__",
            ".archapi",
            "archapi.egg-info",
        }

        for config_key, target_list in hint_map.items():
            raw_dir = self._config.get(config_key)
            if not raw_dir:
                continue

            hint_path = (self.project_path / raw_dir).resolve()

            if not hint_path.exists() or not hint_path.is_dir():
                continue

            for file_path in hint_path.rglob("*"):
                if not file_path.is_file():
                    continue

                try:
                    rel_parts = file_path.relative_to(self.project_path).parts
                except ValueError:
                    rel_parts = file_path.parts

                if any(part in ignored_parts for part in rel_parts):
                    continue

                if file_path not in target_list:
                    target_list.append(file_path)

    def config(self) -> Dict[str, Any]:
        return dict(self._config)

    def build_maps(self) -> Dict[str, Any]:
        scan = self._scan or self.scan()
        adapter = self._adapter()
        self._maps = adapter.build_maps(scan)
        return self._maps

    def extract_genome(self) -> APIGenome:
        scan = self._scan or self.scan()
        maps = self._maps or self.build_maps()
        adapter = self._adapter()
        self._genome = adapter.extract_genome(maps, scan)
        self._genome.framework = (self._detection or self.detect_framework()).framework
        return self._genome

    def compute_confidence(self) -> Dict[str, Any]:
        detection = self._detection or self.detect_framework()
        genome = self._genome or self.extract_genome()

        missing = []

        if genome.route_style == "unknown":
            missing.append("route style")
        if genome.controller_style == "unknown":
            missing.append("controller style")
        if genome.service_style == "unknown":
            missing.append("service style")
        if genome.schema_style == "unknown":
            missing.append("schema style")

        # Overall confidence should consider BOTH:
        # 1. framework detection confidence
        # 2. API architecture/genome confidence
        #
        # This prevents generic/unknown projects from being treated as safe
        # just because some folders accidentally look like routes/services.
        overall = round(min(detection.confidence, genome.confidence), 2)

        mode = "generate"

        if detection.framework in {"generic", "node-unknown"}:
            mode = "blocked"
        elif overall < 0.30:
            mode = "blocked"
        elif overall < 0.55:
            mode = "plan_only"
        elif overall < 0.75:
            mode = "generate_with_warnings"

        return {
            "overall": overall,
            "detection_confidence": detection.confidence,
            "genome_confidence": genome.confidence,
            "mode": mode,
            "missing": missing,
            "framework": genome.framework,
        }

    def plan_api(self, request: str) -> APIPlan:
        maps = self._maps or self.build_maps()
        genome = self._genome or self.extract_genome()
        adapter = self._adapter()

        plan = adapter.plan_api(request, genome, maps)
        confidence = self.compute_confidence()

        if confidence["mode"] in {"blocked", "plan_only"}:
            plan.generation_allowed = False

            if confidence["framework"] in {"generic", "node-unknown"}:
                plan.reason = (
                    "Framework could not be confidently detected. "
                    "Provide framework or config before generation."
                )
            else:
                plan.reason = (
                    "Architecture confidence too low for code generation. "
                    f"Missing: {', '.join(confidence['missing']) or 'unknown'}"
                )

        return plan

    def save_cache(self) -> Dict[str, Path]:
        detection = self._detection or self.detect_framework()
        scan = self._scan or self.scan()
        maps = self._maps or self.build_maps()
        genome = self._genome or self.extract_genome()

        return self._cache.save_snapshot(
            detection=detection,
            scan=scan,
            maps=maps,
            genome=genome,
        )

    def changed_files(self) -> list:
        return self._cache.changed_files()

    def scan_secrets(self):
        return self._secret_scanner.scan()

    def redact_context(self, text: str) -> str:
        return self._context_redactor.redact(text)

    def validate_policy(self, result: GenerationResult):
        return self._policy_gate.validate_result(result)

    def score_architecture(self, result: GenerationResult):
        genome = self._genome or self.extract_genome()
        return self._architecture_scorer.score(result.files, genome)

    def validate_project_commands(self):
        detection = self._detection or self.detect_framework()

        if detection.framework in {"express-typescript", "nestjs", "node-unknown"}:
            return self._command_validator.validate_node_project()

        # Python-based frameworks use Python project validation
        if detection.framework in {"fastapi", "flask", "django-drf"}:
            return self._command_validator.validate_python_project()

        # Default fallback for unrecognised frameworks
        return self._command_validator.validate_node_project()

    def generate_api(self, request: str, dry_run: bool = True) -> GenerationResult:
        if self._use_llm:
            return self._generate_with_llm(request, dry_run=dry_run)
        return self._generate_deterministic(request, dry_run=dry_run)

    # ------------------------------------------------------------------
    # Deterministic generation path (original behaviour)
    # ------------------------------------------------------------------

    def _generate_deterministic(self, request: str, dry_run: bool = True) -> GenerationResult:
        maps = self._maps or self.build_maps()
        genome = self._genome or self.extract_genome()
        plan = self.plan_api(request)

        adapter = self._adapter()
        files = adapter.generate_code(plan, genome, maps)
        report = adapter.validate_generated_code(files, plan, genome)

        result = GenerationResult(
            project_path=self.project_path,
            plan=plan,
            files=files,
            validation_report=report,
            warnings=report.warnings,
        )

        if not dry_run and report.success:
            result.apply()

        return result

    # ------------------------------------------------------------------
    # LLM-first generation path (Phase 5)
    # ------------------------------------------------------------------

    def _generate_with_llm(self, request: str, dry_run: bool = True) -> GenerationResult:
        """Generate API files using an LLM with architecture-aware prompting."""
        from archapi.llm.prompt_builder import PromptBuilder
        from archapi.llm.response_parser import ResponseParser
        from archapi.llm.errors import LLMProviderError, LLMParseError

        genome = self._genome or self.extract_genome()
        scan = self._scan or self.scan()

        llm = self._resolve_llm()

        prompt = PromptBuilder().build(request, genome, scan)

        try:
            raw_response = llm.complete(prompt)
        except LLMProviderError as exc:
            # Return a blocked result rather than raising, so callers can inspect
            empty_plan = APIPlan(
                request=request,
                method="GET",
                path="/",
                entities=[],
                layers=[],
                generation_allowed=False,
                reason=f"LLM provider error: {exc}",
            )
            return GenerationResult(
                project_path=self.project_path,
                plan=empty_plan,
                files=[],
                validation_report=ValidationReport(
                    success=False,
                    errors=[str(exc)],
                ),
            )

        try:
            plan, files = ResponseParser().parse(raw_response)
        except Exception as exc:
            fallback_plan = self.plan_api(request)
            fallback_plan.generation_allowed = False
            fallback_plan.reason = f"LLM response could not be parsed: {exc}"

            return GenerationResult(
                project_path=self.project_path,
                plan=fallback_plan,
                files=[],
                validation_report=ValidationReport(
                    success=False,
                    errors=[fallback_plan.reason],
                    warnings=[],
                ),
                warnings=[],
            )
        except LLMParseError as exc:
            empty_plan = APIPlan(
                request=request,
                method="GET",
                path="/",
                entities=[],
                layers=[],
                generation_allowed=False,
                reason=f"LLM parse error: {exc}",
            )
            return GenerationResult(
                project_path=self.project_path,
                plan=empty_plan,
                files=[],
                validation_report=ValidationReport(
                    success=False,
                    errors=[str(exc)],
                ),
            )

        # Stamp the request onto the plan
        plan.request = request

        # Run safety checks
        warnings: List[str] = []
        policy = self._policy_gate.validate_result(
            GenerationResult(
                project_path=self.project_path,
                plan=plan,
                files=files,
                validation_report=ValidationReport(success=True),
            )
        )
        if not policy.allowed:
            plan.generation_allowed = False
            plan.reason = "; ".join(policy.errors)

        # Architecture consistency score
        arch_score = self._architecture_scorer.score(files, genome)
        if arch_score.percentage < 50:
            warnings.append(
                f"Architecture consistency score is low ({arch_score.percentage:.0f}%). "
                "Review generated files carefully."
            )

        report = ValidationReport(
            success=plan.generation_allowed and policy.allowed,
            errors=policy.errors if not policy.allowed else [],
            warnings=warnings,
        )

        result = GenerationResult(
            project_path=self.project_path,
            plan=plan,
            files=files,
            validation_report=report,
            warnings=warnings,
        )

        if not dry_run and report.success:
            result.apply()

        return result

    def _resolve_llm(self):
        """Lazily initialise the LLM provider if not already set."""
        if self._llm is not None:
            return self._llm

        from archapi.llm.openai_provider import OpenAIProvider
        self._llm = OpenAIProvider(model=self._llm_model, api_key=self._api_key)
        return self._llm
