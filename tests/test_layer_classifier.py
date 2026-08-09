import tempfile
import unittest
from pathlib import Path

from archapi.frameworks.generic import GenericAdapter
from archapi.mapping.layer_classifier import LayerClassifier


class TestLayerClassifierBasics(unittest.TestCase):
    def setUp(self):
        self.classifier = LayerClassifier()

    def _layer(self, relative_path: str, framework=None) -> str:
        return self.classifier.classify(relative_path, framework=framework).layer

    def test_schema_layer(self):
        self.assertEqual(self._layer("app/schemas/user.py"), "schema")

    def test_service_layer(self):
        self.assertEqual(self._layer("src/services/auth.service.ts"), "service")

    def test_middleware_layer(self):
        self.assertEqual(self._layer("src/middleware/auth.ts"), "middleware")

    def test_model_layer(self):
        self.assertEqual(self._layer("src/models/order.ts"), "model")

    def test_route_layer(self):
        self.assertEqual(self._layer("app/routers/refund_router.py"), "route")
        self.assertEqual(self._layer("api/urls.py"), "route")

    def test_controller_layer(self):
        self.assertEqual(self._layer("src/controllers/user.controller.ts"), "controller")
        self.assertEqual(self._layer("api/views.py"), "controller")

    def test_config_layer_exact_filename_match(self):
        for filename in ("package.json", "requirements.txt", "pyproject.toml", "Dockerfile"):
            self.assertEqual(self._layer(filename), "config", filename)

    def test_unknown_fallback(self):
        self.assertEqual(self._layer("README.md"), "unknown")
        self.assertEqual(self._layer("src/user/user.module.ts"), "unknown")

    def test_rejects_absolute_path(self):
        with self.assertRaises(ValueError):
            self.classifier.classify("/abs/path/app/schemas/user.py")

    def test_reason_and_matched_token_are_explainable(self):
        classification = self.classifier.classify("app/schemas/user.py")
        self.assertEqual(classification.layer, "schema")
        self.assertTrue(classification.reason)
        self.assertEqual(classification.matched_token, "schemas")

        unknown = self.classifier.classify("README.md")
        self.assertIsNone(unknown.matched_token)

    def test_framework_hint_does_not_change_generic_result(self):
        path = "app/schemas/refund.py"
        self.assertEqual(self._layer(path, framework=None), self._layer(path, framework="fastapi"))
        self.assertEqual(self._layer(path, framework="fastapi"), self._layer(path, framework="django-drf"))


class TestLayerClassifierPrecedence(unittest.TestCase):
    """Ambiguous cases: structural test signals must win over weaker keyword
    signals like a filename containing "service"."""

    def setUp(self):
        self.classifier = LayerClassifier()

    def test_test_file_with_service_in_name_is_still_a_test(self):
        classification = self.classifier.classify("tests/test_refund_service.py")
        self.assertEqual(classification.layer, "test")

    def test_singular_test_directory_is_recognized(self):
        classification = self.classifier.classify("test/user.spec.ts")
        self.assertEqual(classification.layer, "test")

    def test_directory_signal_wins_over_conflicting_filename_token(self):
        # Filename suggests "service" but the file lives under controllers/;
        # the immediate containing directory is the stronger signal.
        classification = self.classifier.classify("src/controllers/user.service.ts")
        self.assertEqual(classification.layer, "controller")


class TestLayerClassifierRootNameInvariance(unittest.TestCase):
    """
    Regression coverage for the exact bug discovered in Phase 7A: a project
    root directory name that happens to embed a layer keyword ("entity",
    "service", etc.) must never distort classification of files inside it.
    """

    def setUp(self):
        self.classifier = LayerClassifier()

    def test_identity_service_root_does_not_leak_into_schema_classification(self):
        # "identity-service" contains both "entity" (inside "identity") and
        # "service" as literal substrings -- exactly the old bug's trigger.
        classification = self.classifier.classify(
            "identity-service/app/schemas/refund.py"
        )
        self.assertEqual(classification.layer, "schema")

    def test_enterprise_api_root_does_not_leak_into_test_classification(self):
        classification = self.classifier.classify("enterprise-api/tests/test_user.py")
        self.assertEqual(classification.layer, "test")

    def test_authentication_root_does_not_leak_into_service_classification(self):
        classification = self.classifier.classify("authentication/app/services/user.py")
        self.assertEqual(classification.layer, "service")


# ===========================================================================
# End-to-end regression test through GenericAdapter.scan(), reproducing the
# same internal project structure under differently named repository roots.
# ===========================================================================

def _build_internal_structure(root: Path, dirname: str) -> Path:
    project = root / dirname

    (project / "app/schemas").mkdir(parents=True, exist_ok=True)
    (project / "app/services").mkdir(parents=True, exist_ok=True)
    (project / "app/middleware").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)

    (project / "app/schemas/refund.py").write_text("class RefundSchema:\n    pass\n")
    (project / "app/services/user.py").write_text("class UserService:\n    pass\n")
    (project / "app/middleware/auth.py").write_text("def guard():\n    pass\n")
    (project / "tests/test_user.py").write_text("def test_x():\n    assert True\n")

    return project


class TestScanRootNameInvariance(unittest.TestCase):
    def test_identical_classification_across_differently_named_roots(self):
        root_names = ["identity-service", "enterprise-api", "sample_project"]
        results = {}

        with tempfile.TemporaryDirectory() as tmp:
            for name in root_names:
                project = _build_internal_structure(Path(tmp), name)
                scan = GenericAdapter().scan(project)

                results[name] = {
                    bucket: sorted(str(p.relative_to(project)) for p in getattr(scan, bucket))
                    for bucket in (
                        "routes", "controllers", "services", "models",
                        "schemas", "middleware", "tests", "unknown",
                    )
                }

        baseline = results["identity-service"]
        for name in root_names[1:]:
            self.assertEqual(
                results[name], baseline,
                f"Classification differs between 'identity-service' and '{name}'",
            )

        # Pin the actually-expected buckets too, so all three roots agreeing
        # on a still-wrong classification wouldn't silently pass.
        self.assertEqual(baseline["schemas"], ["app/schemas/refund.py"])
        self.assertEqual(baseline["services"], ["app/services/user.py"])
        self.assertEqual(baseline["middleware"], ["app/middleware/auth.py"])
        self.assertEqual(baseline["tests"], ["tests/test_user.py"])
        self.assertEqual(baseline["models"], [])
        self.assertEqual(baseline["routes"], [])
        self.assertEqual(baseline["controllers"], [])
        self.assertEqual(baseline["unknown"], [])


if __name__ == "__main__":
    unittest.main()
