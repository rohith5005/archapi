from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from archapi.config import ArchAPIConfig, ArchAPIConfigError
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


def _emit(message: str) -> None:
    # No-op progress hook; kept as a call site for a future progress callback.
    pass


class ArchAPI:
    def __init__(
        self,
        project_path: Union[str, Path],
        framework: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
        llm_model: Optional[str] = None,
        llm_provider=None,
        api_key: Optional[str] = None,
        settings: Optional[ArchAPIConfig] = None,
    ):
        """
        :param config: Architecture hints (route_dir/service_dir/...) for
            "strict config mode" scanning. Predates and is unrelated to
            `settings` below -- kept as its own parameter so existing
            callers are unaffected.
        :param settings: Central ArchAPIConfig (Phase 8C) -- LLM
            provider/model, retrieval budget, strict_validation. Defaults
            to ArchAPIConfig() (safe, use_llm=False). `use_llm=True` or an
            explicit `llm_model=` passed directly here always takes
            precedence over `settings`, for full backward compatibility
            with existing direct-construction callers that never touch
            ArchAPIConfig at all.
        """
        self.project_path = Path(project_path).resolve()
        if not self.project_path.exists():
            raise FileNotFoundError(f"Project path does not exist: {self.project_path}")

        self._framework_override = framework
        self._config = config or {}
        self._settings = settings or ArchAPIConfig()
        self._use_llm = bool(use_llm) or self._settings.use_llm
        self._llm_model = llm_model or self._settings.llm_model
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

        # Set by the LLM generation path; kept for research instrumentation
        # (Phase 7 Step 15) so retrieval decisions remain inspectable after
        # generation without re-deriving them.
        self._last_retrieved_context = None

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

    def settings(self) -> ArchAPIConfig:
        """The resolved ArchAPIConfig (Phase 8C) this instance is using."""
        return self._settings

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
        scan = self._scan or self.scan()

        _emit("planning API")
        plan = self.plan_api(request)

        _emit("generating code")
        adapter = self._adapter()
        files = adapter.generate_code(plan, genome, maps)

        _emit("validating output")
        report = adapter.validate_generated_code(files, plan, genome, scan=scan)
        framework_validation_pass = report.success

        policy = self._policy_gate.validate_files(files, plan)
        report.errors.extend(policy.errors)
        report.warnings.extend(policy.warnings)
        report.success = report.success and policy.allowed

        self._apply_strict_validation(report)

        result = GenerationResult(
            project_path=self.project_path,
            plan=plan,
            files=files,
            validation_report=report,
            warnings=report.warnings,
            policy_gate_pass=policy.allowed,
            framework_validation_pass=framework_validation_pass,
        )

        if not dry_run and report.success:
            _emit("writing files")
            result.apply()

        _emit("done")
        return result

    # ------------------------------------------------------------------
    # LLM-first generation path (Phase 5)
    # ------------------------------------------------------------------

    def _generate_with_llm(self, request: str, dry_run: bool = True) -> GenerationResult:
        """Generate API files using an LLM with architecture-aware prompting."""
        from archapi.llm.prompt_builder import PromptBuilder
        from archapi.llm.response_parser import ResponseParser
        from archapi.llm.errors import LLMProviderError, LLMParseError
        from archapi.indexing.repository_index import build_repository_index
        from archapi.indexing.context_retriever import ContextRetriever

        genome = self._genome or self.extract_genome()
        scan = self._scan or self.scan()
        maps = self._maps or self.build_maps()

        llm = self._resolve_llm()

        # A deterministic plan hint (method/path/entities/layers) purely to
        # drive retrieval and to show the model what was inferred from the
        # request. This is separate from -- and does not gate -- the final
        # plan, which still comes from parsing the LLM's own JSON response
        # below; a low-confidence hint must not silently block LLM
        # generation the way it does on the deterministic path.
        adapter = self._adapter()
        plan_hint = adapter.plan_api(request, genome, maps)

        index = build_repository_index(scan, genome)
        retrieved_context = ContextRetriever(budget=self._settings.to_context_budget()).retrieve(
            request=request, plan=plan_hint, index=index
        )
        self._last_retrieved_context = retrieved_context

        prompt = PromptBuilder().build(
            request, genome, plan=plan_hint, retrieved_context=retrieved_context
        )
        prompt = self._context_redactor.redact(prompt)

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
                policy_gate_pass=False,
                framework_validation_pass=False,
            )

        try:
            plan, files = ResponseParser().parse(raw_response)
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
                policy_gate_pass=False,
                framework_validation_pass=False,
            )

        # Stamp the request onto the plan
        plan.request = request

        # Same structural validation the deterministic path gets: required
        # layers present, no empty files, etc.
        adapter = self._adapter()
        report = adapter.validate_generated_code(files, plan, genome, scan=scan)
        framework_validation_pass = report.success

        # Output safety gate: path containment, protected/bootstrap/config
        # files, unrequested middleware, embedded secrets.
        policy = self._policy_gate.validate_files(files, plan)
        report.errors.extend(policy.errors)
        report.warnings.extend(policy.warnings)
        report.success = report.success and policy.allowed

        # Architecture consistency score
        arch_score = self._architecture_scorer.score(files, genome)
        if arch_score.percentage < 50:
            report.warnings.append(
                f"Architecture consistency score is low ({arch_score.percentage:.0f}%). "
                "Review generated files carefully."
            )

        self._apply_strict_validation(report)

        plan.generation_allowed = report.success
        if not report.success:
            plan.reason = "; ".join(report.errors)

        result = GenerationResult(
            project_path=self.project_path,
            plan=plan,
            files=files,
            validation_report=report,
            warnings=report.warnings,
            policy_gate_pass=policy.allowed,
            framework_validation_pass=framework_validation_pass,
        )

        if not dry_run and report.success:
            result.apply()

        return result

    def _resolve_llm(self):
        """Lazily initialise the LLM provider if not already set."""
        if self._llm is not None:
            return self._llm

        provider_name = self._settings.llm_provider
        if provider_name == "openai":
            from archapi.llm.openai_provider import OpenAIProvider
            self._llm = OpenAIProvider(model=self._llm_model, api_key=self._api_key)
        else:
            # ArchAPIConfig.__post_init__ already validates this against
            # KNOWN_LLM_PROVIDERS at construction time; this branch only
            # matters if a provider is ever added to that set without a
            # matching case here.
            raise ArchAPIConfigError(f"No provider implementation wired up for: {provider_name!r}")

        return self._llm

    def _apply_strict_validation(self, report: ValidationReport) -> None:
        """
        Optional extra caution (Phase 8C, off by default): escalate
        non-fatal validation warnings -- e.g. the Phase 8A
        naming-consistency warning -- into blocking errors. Never touches
        PolicyGate or framework-validation *errors*, which always block
        regardless of this setting.
        """
        if self._settings.strict_validation and report.warnings:
            report.errors.extend(report.warnings)
            report.success = False
