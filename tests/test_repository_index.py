import tempfile
import unittest
from pathlib import Path

from archapi.frameworks.generic import GenericAdapter
from archapi.indexing.repository_index import (
    _MAX_SOURCE_FILE_BYTES,
    _RECOGNIZED_SUFFIXES,
    RepositoryIndex,
    build_repository_index,
)


# ===========================================================================
# Fixture: a small multi-entity FastAPI-shaped project.
#
# Deliberately includes three parallel entities (refund/order/user) so that
# entity-term extraction and query helpers can be tested meaningfully, plus
# one unrecognized-extension file and one oversized file to exercise the
# suffix and size filters.
# ===========================================================================

def create_multi_entity_project(root: Path) -> Path:
    # Deliberately avoids substrings ("entity", "model", "route", "service",
    # "schema", etc.) that would collide with GenericAdapter's path-substring
    # bucket classifier and misclassify every file under this directory.
    project = root / "sample_refund_api"

    (project / "app/routers").mkdir(parents=True, exist_ok=True)
    (project / "app/services").mkdir(parents=True, exist_ok=True)
    (project / "app/schemas").mkdir(parents=True, exist_ok=True)
    (project / "app/middleware").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)

    (project / "app/routers/refund_router.py").write_text(
        "from fastapi import APIRouter, Depends\n"
        "from app.schemas.refund_schema import RefundRequest, RefundResponse\n"
        "from app.services.refund_service import refund_service\n"
        "from app.middleware.auth_middleware import get_current_user\n\n"
        "router = APIRouter()\n\n\n"
        '@router.post("/refunds", response_model=RefundResponse)\n'
        "async def create_refund(payload: RefundRequest, user=Depends(get_current_user)):\n"
        "    return await refund_service.execute(payload)\n"
    )

    (project / "app/services/refund_service.py").write_text(
        "from app.schemas.refund_schema import RefundRequest, RefundResponse\n\n\n"
        "class RefundService:\n"
        "    async def execute(self, payload: RefundRequest) -> RefundResponse:\n"
        "        return RefundResponse(message='ok')\n\n\n"
        "refund_service = RefundService()\n"
    )

    (project / "app/schemas/refund_schema.py").write_text(
        "from pydantic import BaseModel, validator\n\n\n"
        "class RefundRequest(BaseModel):\n"
        "    order_id: str\n"
        "    amount: float\n\n"
        '    @validator("amount")\n'
        "    def validate_amount(cls, value):\n"
        "        if value <= 0:\n"
        "            raise ValueError('amount must be positive')\n"
        "        return value\n\n\n"
        "class RefundResponse(BaseModel):\n"
        "    message: str\n"
    )

    (project / "tests/test_refund.py").write_text(
        "def test_create_refund_placeholder():\n"
        "    assert True\n"
    )

    (project / "app/routers/order_router.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n\n"
        '@router.get("/orders/{order_id}")\n'
        "async def get_order(order_id: str):\n"
        "    return {'id': order_id}\n"
    )

    (project / "app/services/order_service.py").write_text(
        "class OrderService:\n"
        "    async def execute(self):\n"
        "        return {}\n\n\n"
        "order_service = OrderService()\n"
    )

    (project / "app/routers/user_router.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n\n"
        '@router.get("/users/{user_id}")\n'
        "async def get_user(user_id: str):\n"
        "    return {'id': user_id}\n"
    )

    (project / "app/services/user_service.py").write_text(
        "class UserService:\n"
        "    async def execute(self):\n"
        "        return {}\n\n\n"
        "user_service = UserService()\n"
    )

    (project / "app/middleware/auth_middleware.py").write_text(
        "def get_current_user():\n"
        "    # Validates the bearer token and returns the authenticated user.\n"
        "    return {'id': 'demo'}\n"
    )

    # Unrecognized extension inside a route-classified directory: must be
    # scanned (matched by GenericAdapter's "route" keyword) but excluded
    # from the index because ".rb" is not a recognized source extension.
    (project / "app/routers/legacy_route.rb").write_text(
        "# legacy ruby route, should never be indexed\n"
    )

    # Oversized file inside a service-classified directory: must be excluded
    # by the max-source-file-size guard.
    (project / "app/services/huge_service.py").write_text(
        "class HugeService:\n    pass\n" + ("# padding\n" * (_MAX_SOURCE_FILE_BYTES // 9 + 100))
    )

    return project


class TestRepositoryIndexCore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_multi_entity_project(Path(self._tmp.name))
        self.scan = GenericAdapter().scan(self.project)
        self.index = build_repository_index(self.scan, genome=None)

    def test_recognized_files_all_indexed_and_others_excluded(self):
        expected_paths = {
            str(path.relative_to(self.project))
            for bucket in (
                self.scan.routes, self.scan.controllers, self.scan.services,
                self.scan.models, self.scan.schemas, self.scan.middleware,
                self.scan.tests,
            )
            for path in bucket
            if path.suffix.lower() in _RECOGNIZED_SUFFIXES
            and path.stat().st_size <= _MAX_SOURCE_FILE_BYTES
        }
        actual_paths = {str(unit.path) for unit in self.index.units}

        self.assertEqual(actual_paths, expected_paths)
        self.assertNotIn("app/routers/legacy_route.rb", actual_paths)
        self.assertFalse(any("huge_service" in p for p in actual_paths))

    def test_layer_assignment_matches_scan_bucket(self):
        refund_router = self.index.find_by_path("app/routers/refund_router.py")
        refund_service = self.index.find_by_path("app/services/refund_service.py")
        refund_schema = self.index.find_by_path("app/schemas/refund_schema.py")
        auth_middleware = self.index.find_by_path("app/middleware/auth_middleware.py")
        refund_test = self.index.find_by_path("tests/test_refund.py")

        self.assertEqual(refund_router.layer, "route")
        self.assertEqual(refund_service.layer, "service")
        self.assertEqual(refund_schema.layer, "schema")
        self.assertEqual(auth_middleware.layer, "middleware")
        self.assertEqual(refund_test.layer, "test")

    def test_language_detection(self):
        for unit in self.index.units:
            self.assertEqual(unit.language, "python")

    def test_http_method_and_route_path_extraction(self):
        refund_router = self.index.find_by_path("app/routers/refund_router.py")
        order_router = self.index.find_by_path("app/routers/order_router.py")

        self.assertEqual(refund_router.http_methods, ["POST"])
        self.assertEqual(refund_router.route_paths, ["/refunds"])
        self.assertEqual(order_router.http_methods, ["GET"])
        self.assertEqual(order_router.route_paths, ["/orders/{order_id}"])

    def test_imports_captured(self):
        refund_service = self.index.find_by_path("app/services/refund_service.py")
        self.assertIn("app.schemas.refund_schema", refund_service.imports)

    def test_entity_terms_derived_from_filename(self):
        refund_router = self.index.find_by_path("app/routers/refund_router.py")
        order_service = self.index.find_by_path("app/services/order_service.py")
        user_router = self.index.find_by_path("app/routers/user_router.py")

        self.assertEqual(refund_router.entity_terms, ["refund"])
        self.assertEqual(order_service.entity_terms, ["order"])
        self.assertEqual(user_router.entity_terms, ["user"])

    def test_auth_indicators_detected(self):
        auth_middleware = self.index.find_by_path("app/middleware/auth_middleware.py")
        order_service = self.index.find_by_path("app/services/order_service.py")

        self.assertIn("auth", auth_middleware.auth_indicators)
        self.assertEqual(order_service.auth_indicators, [])

    def test_validation_indicators_detected(self):
        refund_schema = self.index.find_by_path("app/schemas/refund_schema.py")

        self.assertIn("basemodel", refund_schema.validation_indicators)
        self.assertIn("pydantic", refund_schema.validation_indicators)
        self.assertIn("validate", refund_schema.validation_indicators)

    def test_symbols_include_classes_and_functions(self):
        refund_service = self.index.find_by_path("app/services/refund_service.py")
        refund_schema = self.index.find_by_path("app/schemas/refund_schema.py")

        self.assertIn("RefundService", refund_service.symbols)
        self.assertIn("execute", refund_service.symbols)
        self.assertIn("RefundRequest", refund_schema.symbols)
        self.assertIn("RefundResponse", refund_schema.symbols)
        self.assertIn("validate_amount", refund_schema.symbols)

    def test_is_test_flag(self):
        refund_test = self.index.find_by_path("tests/test_refund.py")
        refund_router = self.index.find_by_path("app/routers/refund_router.py")

        self.assertTrue(refund_test.is_test)
        self.assertFalse(refund_router.is_test)

    def test_snippet_bounded_and_nonempty(self):
        for unit in self.index.units:
            self.assertTrue(unit.snippet)
            self.assertLessEqual(len(unit.snippet), 803)  # _MAX_SNIPPET_CHARS + "..."

    def test_query_helpers(self):
        self.assertEqual(
            {u.layer for u in self.index.by_layer("route")}, {"route"}
        )
        self.assertTrue(all(u.layer == "route" for u in self.index.by_layer("route")))

        post_units = self.index.with_http_method("POST")
        self.assertEqual({str(u.path) for u in post_units}, {"app/routers/refund_router.py"})

        refund_units = self.index.with_entity_term("refund")
        self.assertEqual(
            {str(u.path) for u in refund_units},
            {
                "app/routers/refund_router.py",
                "app/services/refund_service.py",
                "app/schemas/refund_schema.py",
                "tests/test_refund.py",
            },
        )

        self.assertIsNone(self.index.find_by_path("does/not/exist.py"))
        self.assertEqual(len(self.index), len(self.index.units))

    def test_determinism_across_rebuilds(self):
        rebuilt = build_repository_index(self.scan, genome=None)
        self.assertEqual(self.index.units, rebuilt.units)

    def test_stable_ordering(self):
        ordering = [(unit.layer, str(unit.path)) for unit in self.index.units]
        self.assertEqual(ordering, sorted(ordering))


class TestRepositoryIndexFrameworkCoverage(unittest.TestCase):
    """Smoke coverage across the frameworks ArchAPI already supports."""

    def test_express_typescript_project_indexes_without_error(self):
        from tests.test_archapi_suite import create_express_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_express_project(Path(tmp))
            scan = GenericAdapter().scan(project)
            index = build_repository_index(scan, genome=None)

            self.assertGreater(len(index), 0)
            self.assertTrue(all(u.language in {"typescript"} for u in index.units))

    def test_fastapi_project_indexes_without_error(self):
        from tests.test_archapi_suite import create_fastapi_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_fastapi_project(Path(tmp))
            scan = GenericAdapter().scan(project)
            index = build_repository_index(scan, genome=None)

            self.assertGreater(len(index), 0)
            self.assertTrue(all(u.language == "python" for u in index.units))

    def test_flask_project_indexes_without_error(self):
        from tests.test_archapi_suite import create_flask_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_flask_project(Path(tmp))
            scan = GenericAdapter().scan(project)
            index = build_repository_index(scan, genome=None)

            self.assertGreater(len(index), 0)

    def test_nestjs_project_indexes_without_error(self):
        from tests.test_archapi_suite import create_nestjs_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_nestjs_project(Path(tmp))
            scan = GenericAdapter().scan(project)
            index = build_repository_index(scan, genome=None)

            self.assertGreater(len(index), 0)
            controller_unit = index.find_by_path("src/user/user.controller.ts")
            self.assertIsNotNone(controller_unit)
            self.assertIn("GET", controller_unit.http_methods)

    def test_django_drf_project_indexes_without_error(self):
        from tests.test_archapi_suite import create_django_drf_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_django_drf_project(Path(tmp))
            scan = GenericAdapter().scan(project)
            index = build_repository_index(scan, genome=None)

            self.assertGreater(len(index), 0)
            views_unit = index.find_by_path("api/views.py")
            self.assertIsNotNone(views_unit)
            self.assertIn("GET", views_unit.http_methods)


if __name__ == "__main__":
    unittest.main()
