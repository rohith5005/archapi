import unittest

from archapi import ArchAPI


class TestExpressGeneration(unittest.TestCase):
    def test_express_detection_and_generation(self):
        engine = ArchAPI("./sample_projects/express_basic")

        detection = engine.detect_framework()
        result = engine.generate_api("Create POST API for product review", dry_run=True)
        score = engine.score_architecture(result)

        self.assertEqual(detection.framework, "express-typescript")
        self.assertTrue(result.validation_report.success)
        self.assertEqual(result.plan.method, "POST")
        self.assertEqual(result.plan.path, "/products/{product_id}/reviews")
        self.assertEqual(len(result.files), 5)
        self.assertEqual(score.percentage, 100.0)
        self.assertIn('router.post("/products/:productId/reviews"', result.files[0].content)


class TestFastAPIGeneration(unittest.TestCase):
    def test_fastapi_detection_and_generation(self):
        engine = ArchAPI("./sample_projects/fastapi_basic")

        detection = engine.detect_framework()
        result = engine.generate_api("Create GET API for payment status", dry_run=True)
        score = engine.score_architecture(result)

        self.assertEqual(detection.framework, "fastapi")
        self.assertTrue(result.validation_report.success)
        self.assertEqual(result.plan.method, "GET")
        self.assertEqual(result.plan.path, "/payments/{id}/status")
        self.assertEqual(len(result.files), 4)
        self.assertEqual(score.percentage, 100.0)
        self.assertIn('@router.get("/payments/{id}/status"', result.files[0].content)


class TestStrictConfigMode(unittest.TestCase):
    def test_express_strict_config(self):
        engine = ArchAPI(
            ".",
            framework="express-typescript",
            config={
                "route_dir": "sample_projects/express_basic/src/routes",
                "controller_dir": "sample_projects/express_basic/src/controllers",
                "service_dir": "sample_projects/express_basic/src/services",
                "model_dir": "sample_projects/express_basic/src/models",
                "schema_dir": "sample_projects/express_basic/src/schemas",
                "middleware_dir": "sample_projects/express_basic/src/middleware",
                "test_dir": "sample_projects/express_basic/tests",
            },
        )

        scan = engine.scan()
        result = engine.generate_api("Create POST API for product review", dry_run=True)

        self.assertEqual(len(scan.unknown), 0)
        self.assertTrue(result.validation_report.success)

    def test_fastapi_strict_config(self):
        engine = ArchAPI(
            ".",
            framework="fastapi",
            config={
                "route_dir": "sample_projects/fastapi_basic/app/routers",
                "service_dir": "sample_projects/fastapi_basic/app/services",
                "schema_dir": "sample_projects/fastapi_basic/app/schemas",
                "test_dir": "sample_projects/fastapi_basic/tests",
            },
        )

        scan = engine.scan()
        result = engine.generate_api("Create POST API for product review", dry_run=True)

        self.assertEqual(len(scan.unknown), 0)
        self.assertTrue(result.validation_report.success)


class TestSafetyAndUtilities(unittest.TestCase):
    def test_low_confidence_project_is_blocked(self):
        engine = ArchAPI(".")

        plan = engine.plan_api("Create GET API for user order history")
        result = engine.generate_api("Create GET API for user order history", dry_run=True)

        self.assertFalse(plan.generation_allowed)
        self.assertEqual(result.files, [])
        self.assertFalse(result.validation_report.success)
        self.assertIn("Framework could not be confidently detected", plan.reason)

    def test_redaction(self):
        engine = ArchAPI("./sample_projects/express_basic")

        redacted = engine.redact_context(
            'API_KEY="1234567890abcdef" TOKEN="abcdef1234567890" SECRET="abcdef1234567890"'
        )

        self.assertIn("[REDACTED_API_KEY]", redacted)
        self.assertIn("[REDACTED_TOKEN]", redacted)
        self.assertIn("[REDACTED_SECRET]", redacted)

    def test_policy_validation(self):
        engine = ArchAPI("./sample_projects/express_basic")

        result = engine.generate_api("Create GET API for payment status", dry_run=True)
        policy = engine.validate_policy(result)

        self.assertTrue(policy.allowed)
        self.assertEqual(policy.errors, [])


if __name__ == "__main__":
    unittest.main()
