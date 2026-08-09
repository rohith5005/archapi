"""
Phase 8A: framework validators must recognize legitimate naming variance
(most concretely: test-file naming) instead of only one hardcoded pattern,
and should surface -- as a non-blocking warning, not a hard rejection --
when generated code diverges from a convention the repository itself
already demonstrates.

This reproduces the exact regression Phase 7G's real-provider evaluation
found: retrieval faithfully imitated a Django DRF project's own flat
`tests.py` convention (what `django-admin startapp` scaffolds by default),
and DjangoDRFAdapter.validate_generated_code() rejected it for lacking a
literal "test_" substring -- disagreement between repository evidence and
ArchAPI's own validator, not a retrieval failure.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from archapi import ArchAPI
from archapi.frameworks.django_drf_adapter import DjangoDRFAdapter
from archapi.frameworks.express_ts.adapter import ExpressTypeScriptAdapter
from archapi.frameworks.fastapi_adapter import FastAPIAdapter
from archapi.frameworks.flask_adapter import FlaskAdapter
from archapi.frameworks.nestjs.adapter import NestJSAdapter
from archapi.types import APIGenome, APIPlan, GeneratedFile, ScanResult
from tests.test_cross_framework_evaluation import create_django_matrix_project, RESOURCES


def _plan(entities=None) -> APIPlan:
    return APIPlan(
        request="x", method="POST", path="/x",
        entities=entities or ["Widget"], layers=["route", "service", "schema", "test"],
        generation_allowed=True,
    )


def _genome(framework: str, confidence: float = 0.9) -> APIGenome:
    return APIGenome(framework=framework, confidence=confidence)


class TestAlternateTestNamingConventionsNowValidate(unittest.TestCase):
    """The core 8A fix: each adapter now recognizes more than one valid
    test-file naming style, instead of a single hardcoded pattern."""

    def test_fastapi_accepts_suffix_style_test_name(self):
        files = [
            GeneratedFile(Path("app/routers/widget_router.py"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/widget_test.py"), "def test_x(): assert True\n"),  # suffix, not prefix
        ]
        report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"))
        self.assertTrue(report.success, report.errors)

    def test_flask_accepts_suffix_style_test_name(self):
        files = [
            GeneratedFile(Path("app/routes/widget_routes.py"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/widget_test.py"), "def test_x(): assert True\n"),
        ]
        report = FlaskAdapter().validate_generated_code(files, _plan(), _genome("flask"))
        self.assertTrue(report.success, report.errors)

    def test_django_accepts_flat_tests_py_convention(self):
        # Exactly the Phase 7G regression: no "test_" substring anywhere.
        files = [
            GeneratedFile(Path("widgets/views.py"), "x = 1\n"),
            GeneratedFile(Path("widgets/serializers.py"), "x = 1\n"),
            GeneratedFile(Path("widgets/urls.py"), "x = 1\n"),
            GeneratedFile(Path("widgets/tests.py"), "def test_x(): assert True\n"),
        ]
        report = DjangoDRFAdapter().validate_generated_code(files, _plan(), _genome("django-drf"))
        self.assertTrue(report.success, report.errors)

    def test_express_accepts_spec_style_test_name(self):
        files = [
            GeneratedFile(Path("src/routes/widget.routes.ts"), "x\n"),
            GeneratedFile(Path("src/controllers/widget.controller.ts"), "x\n"),
            GeneratedFile(Path("src/services/widget.service.ts"), "x\n"),
            GeneratedFile(Path("src/schemas/widget.schema.ts"), "x\n"),
            GeneratedFile(Path("src/tests/widget.spec.ts"), "x\n"),  # .spec.ts, not .test.ts
        ]
        report = ExpressTypeScriptAdapter().validate_generated_code(files, _plan(), _genome("express-typescript"))
        self.assertTrue(report.success, report.errors)

    def test_nestjs_accepts_test_style_instead_of_spec(self):
        files = [
            GeneratedFile(Path("src/widget/widget.controller.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.service.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.module.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.dto.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.controller.test.ts"), "x\n"),  # .test.ts, not .spec.ts
        ]
        report = NestJSAdapter().validate_generated_code(files, _plan(), _genome("nestjs"))
        self.assertTrue(report.success, report.errors)


class TestDefaultConventionsStillPass(unittest.TestCase):
    """No regression for the common/default naming each adapter's own
    deterministic generator has always produced."""

    def test_fastapi_default_prefix_style_still_passes(self):
        files = [
            GeneratedFile(Path("app/routers/widget_router.py"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/test_widget.py"), "def test_x(): assert True\n"),
        ]
        report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"))
        self.assertTrue(report.success, report.errors)

    def test_django_default_test_prefix_still_passes(self):
        files = [
            GeneratedFile(Path("widgets/views.py"), "x = 1\n"),
            GeneratedFile(Path("widgets/serializers.py"), "x = 1\n"),
            GeneratedFile(Path("widgets/urls.py"), "x = 1\n"),
            GeneratedFile(Path("tests/test_widget.py"), "def test_x(): assert True\n"),
        ]
        report = DjangoDRFAdapter().validate_generated_code(files, _plan(), _genome("django-drf"))
        self.assertTrue(report.success, report.errors)

    def test_nestjs_default_spec_style_still_passes(self):
        files = [
            GeneratedFile(Path("src/widget/widget.controller.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.service.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.module.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.dto.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.controller.spec.ts"), "x\n"),
        ]
        report = NestJSAdapter().validate_generated_code(files, _plan(), _genome("nestjs"))
        self.assertTrue(report.success, report.errors)


class TestMissingTestLayerStillFails(unittest.TestCase):
    """The check is broader, not a no-op -- truly missing test coverage
    must still be rejected."""

    def test_fastapi_missing_test_file_fails(self):
        files = [
            GeneratedFile(Path("app/routers/widget_router.py"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
        ]
        report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"))
        self.assertFalse(report.success)
        self.assertTrue(any("test" in err.lower() for err in report.errors))

    def test_django_missing_test_file_fails(self):
        files = [
            GeneratedFile(Path("widgets/views.py"), "x = 1\n"),
            GeneratedFile(Path("widgets/serializers.py"), "x = 1\n"),
            GeneratedFile(Path("widgets/urls.py"), "x = 1\n"),
        ]
        report = DjangoDRFAdapter().validate_generated_code(files, _plan(), _genome("django-drf"))
        self.assertFalse(report.success)
        self.assertTrue(any("test" in err.lower() for err in report.errors))

    def test_nestjs_missing_module_file_still_fails(self):
        # .module.ts has no legitimate naming alternative -- confirms it
        # remains a hard, unchanged requirement (not swept into the more
        # permissive test-layer generalization).
        files = [
            GeneratedFile(Path("src/widget/widget.controller.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.service.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.dto.ts"), "x\n"),
            GeneratedFile(Path("src/widget/widget.controller.spec.ts"), "x\n"),
        ]
        report = NestJSAdapter().validate_generated_code(files, _plan(), _genome("nestjs"))
        self.assertFalse(report.success)
        self.assertTrue(any(".module.ts" in err for err in report.errors))


class TestNamingConsistencyWarnings(unittest.TestCase):
    def test_warns_when_generated_file_shares_no_token_with_existing_convention(self):
        scan = ScanResult(
            framework="fastapi",
            project_path=Path("/tmp/does-not-matter"),
            routes=[Path("app/routers/user_router.py"), Path("app/routers/order_router.py")],
        )
        files = [
            GeneratedFile(Path("app/routers/widget_router.py"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/test_widget.py"), "def test_x(): assert True\n"),
            # Diverges entirely from the project's established "*_router.py"
            # route-naming style.
            GeneratedFile(Path("app/routers/totally_different_naming.py"), "x = 1\n"),
        ]
        report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"), scan=scan)

        # Non-blocking: still succeeds.
        self.assertTrue(report.success, report.errors)
        self.assertTrue(
            any("naming token" in w and "totally_different_naming.py" in w for w in report.warnings)
        )

    def test_no_warning_when_naming_matches_existing_convention(self):
        scan = ScanResult(
            framework="fastapi",
            project_path=Path("/tmp/does-not-matter"),
            routes=[Path("app/routers/user_router.py"), Path("app/routers/order_router.py")],
        )
        files = [
            GeneratedFile(Path("app/routers/widget_router.py"), "x = 1\n"),  # matches "_router.py" style
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/test_widget.py"), "def test_x(): assert True\n"),
        ]
        report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"), scan=scan)

        self.assertTrue(report.success, report.errors)
        self.assertEqual(report.warnings, [])

    def test_no_warning_and_no_crash_when_scan_is_none(self):
        files = [
            GeneratedFile(Path("app/routers/widget_router.py"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/test_widget.py"), "def test_x(): assert True\n"),
        ]
        report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"))  # scan omitted
        self.assertTrue(report.success, report.errors)
        self.assertEqual(report.warnings, [])

    def test_no_warning_for_a_layer_with_no_repository_evidence_yet(self):
        # scan has zero existing route files -- nothing to compare against,
        # so no consistency warning should fire regardless of naming.
        scan = ScanResult(framework="fastapi", project_path=Path("/tmp/does-not-matter"))
        files = [
            GeneratedFile(Path("app/routers/anything_at_all_router.py"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/test_widget.py"), "def test_x(): assert True\n"),
        ]
        report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"), scan=scan)
        self.assertTrue(report.success, report.errors)
        self.assertEqual(report.warnings, [])


class TestMalformedPathDoesNotCrashValidation(unittest.TestCase):
    """Regression test for a bug introduced (and fixed) while building this
    feature: LayerClassifier raises on absolute paths, but adversarial/
    malformed generated paths reach validate_generated_code *before*
    PolicyGate gets a chance to reject them. Validation must degrade
    gracefully, not crash -- PolicyGate remains the actual security gate
    for this case."""

    def test_absolute_generated_path_does_not_raise(self):
        files = [
            GeneratedFile(Path("/etc/passwd"), "x = 1\n"),
            GeneratedFile(Path("app/services/widget_service.py"), "x = 1\n"),
            GeneratedFile(Path("app/schemas/widget_schema.py"), "x = 1\n"),
            GeneratedFile(Path("tests/test_widget.py"), "def test_x(): assert True\n"),
        ]
        scan = ScanResult(
            framework="fastapi", project_path=Path("/tmp/does-not-matter"),
            routes=[Path("app/routers/user_router.py")],
        )
        try:
            report = FastAPIAdapter().validate_generated_code(files, _plan(), _genome("fastapi"), scan=scan)
        except ValueError:
            self.fail("validate_generated_code raised ValueError on an absolute generated path")
        # Missing an actual route file, so this correctly still fails --
        # the point is that it fails cleanly, not with a traceback.
        self.assertFalse(report.success)


class TestEndToEndDjangoRegressionFixed(unittest.TestCase):
    """Reproduces the exact Phase 7G scenario end-to-end through the real
    ArchAPI pipeline (not just the adapter in isolation): retrieval-aware
    generation that imitates the project's own flat tests.py convention
    must now be accepted."""

    def test_retrieval_aware_generation_matching_flat_tests_convention_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_django_matrix_project(Path(tmp))

            provider = MagicMock()
            provider.complete.return_value = json.dumps({
                "method": "POST", "path": "/invoices",
                "entities": ["invoice"], "layers": ["route", "controller", "schema", "test"],
                "files": [
                    {"path": "invoices/views.py", "content": "class InvoiceView:\n    pass\n"},
                    {"path": "invoices/serializers.py", "content": "class InvoiceSerializer:\n    pass\n"},
                    {"path": "invoices/urls.py", "content": "urlpatterns = []\n"},
                    # Flat convention, matching the fixture's own existing
                    # per-app tests.py files -- this is exactly what the
                    # real GPT-4o-mini run produced in Phase 7G.
                    {"path": "invoices/tests.py", "content": "def test_invoice():\n    assert True\n"},
                ],
            })

            engine = ArchAPI(str(project), use_llm=True, llm_provider=provider)
            result = engine.generate_api("POST invoice API", dry_run=True)

            self.assertTrue(result.validation_report.success, result.validation_report.errors)


if __name__ == "__main__":
    unittest.main()
