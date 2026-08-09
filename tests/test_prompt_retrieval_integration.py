import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from archapi import ArchAPI
from archapi.llm.prompt_builder import PromptBuilder
from archapi.types import APIGenome

# ===========================================================================
# Phase 7E: proves the integration -- retrieval actually reaches the LLM
# prompt, arbitrary paths[0] selection is gone, the security boundary
# (redact-before-transmit) still holds, and Phase 6 enforcement is untouched.
# ===========================================================================


def create_billing_project(root: Path) -> Path:
    """
    A FastAPI-shaped project with two real resources (invoice, shipment)
    plus one deliberately irrelevant, alphabetically-first route
    (aaa_health_router.py). Under the old paths[0] behavior this file would
    have been the "route example" shown to the LLM for *every* request,
    regardless of relevance -- proving that no longer happens is the core
    7E claim.
    """
    project = root / "sample_billing_api"
    for rel_dir in ("app/routers", "app/services", "app/schemas", "app/models", "tests"):
        (project / rel_dir).mkdir(parents=True, exist_ok=True)
    (project / "requirements.txt").write_text("fastapi\npydantic\npytest\n")

    (project / "app/routers/aaa_health_router.py").write_text(
        "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n"
        '@router.get("/health")\n'
        "async def health_check():\n"
        "    return {'status': 'ok'}\n"
    )

    (project / "app/routers/invoice_router.py").write_text(
        "from fastapi import APIRouter\n"
        "from app.schemas.invoice_schema import InvoiceRequest, InvoiceResponse\n"
        "from app.services.invoice_service import invoice_service\n\n"
        "router = APIRouter()\n\n"
        '@router.post("/invoices", response_model=InvoiceResponse)\n'
        "async def create_invoice(payload: InvoiceRequest):\n"
        "    return await invoice_service.execute(payload)\n"
    )
    (project / "app/routers/shipment_router.py").write_text(
        "from fastapi import APIRouter\n"
        "from app.schemas.shipment_schema import ShipmentRequest, ShipmentResponse\n"
        "from app.services.shipment_service import shipment_service\n\n"
        "router = APIRouter()\n\n"
        '@router.post("/shipments", response_model=ShipmentResponse)\n'
        "async def create_shipment(payload: ShipmentRequest):\n"
        "    return await shipment_service.execute(payload)\n"
    )

    (project / "app/services/invoice_service.py").write_text(
        "class InvoiceService:\n    async def execute(self, payload):\n        return {}\n\n"
        "invoice_service = InvoiceService()\n"
    )
    (project / "app/services/shipment_service.py").write_text(
        "class ShipmentService:\n    async def execute(self, payload):\n        return {}\n\n"
        "shipment_service = ShipmentService()\n"
    )

    (project / "app/schemas/invoice_schema.py").write_text(
        "from pydantic import BaseModel\n\n"
        "class InvoiceRequest(BaseModel):\n    amount: float\n\n"
        "class InvoiceResponse(BaseModel):\n    message: str\n"
    )
    (project / "app/schemas/shipment_schema.py").write_text(
        "from pydantic import BaseModel\n\n"
        "class ShipmentRequest(BaseModel):\n    address: str\n\n"
        "class ShipmentResponse(BaseModel):\n    message: str\n"
    )

    (project / "app/models/invoice_model.py").write_text("class Invoice:\n    pass\n")
    (project / "app/models/shipment_model.py").write_text("class Shipment:\n    pass\n")

    (project / "tests/test_invoice.py").write_text("def test_invoice():\n    assert True\n")
    (project / "tests/test_shipment.py").write_text("def test_shipment():\n    assert True\n")

    return project


def _mock_provider(response_files=None) -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = json.dumps({
        "method": "POST",
        "path": "/x",
        "entities": ["x"],
        "layers": ["route", "service", "schema", "test"],
        "files": response_files or [{"path": "app/routers/x.py", "content": "x = 1\n"}],
    })
    return provider


class TestPromptBuilderArbitrarySelectionRemoved(unittest.TestCase):
    def test_scan_parameter_no_longer_exists(self):
        # The old signature took (request, genome, scan) and read
        # scan.routes[0]/scan.services[0]/... directly. That parameter is
        # gone entirely -- PromptBuilder has no path back to arbitrary
        # first-found file selection.
        params = list(inspect.signature(PromptBuilder.build).parameters)
        self.assertNotIn("scan", params)

    def test_no_examples_section_without_retrieved_context(self):
        genome = APIGenome(
            framework="fastapi", route_style="fastapi-apirouter",
            schema_style="pydantic", confidence=0.85,
        )
        prompt = PromptBuilder().build("Create GET API for user orders", genome)
        self.assertNotIn("RELEVANT EXISTING PROJECT EXAMPLES", prompt)


class TestRetrievalReachesPrompt(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_billing_project(Path(self._tmp.name))

    def _generate(self, request: str):
        provider = _mock_provider()
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api(request, dry_run=True)
        prompt = provider.complete.call_args[0][0]
        return engine, result, prompt, provider

    def test_irrelevant_alphabetically_first_route_excluded(self):
        _, _, prompt, _ = self._generate("Create POST API for invoice")
        self.assertNotIn("aaa_health_router.py", prompt)

    def test_relevant_route_reaches_prompt(self):
        _, _, prompt, _ = self._generate("Create POST API for invoice")
        self.assertIn("invoice_router.py", prompt)

    def test_relevant_service_schema_and_test_reach_prompt(self):
        _, _, prompt, _ = self._generate("Create POST API for invoice")
        self.assertIn("invoice_service.py", prompt)
        self.assertIn("invoice_schema.py", prompt)
        self.assertIn("test_invoice.py", prompt)
        self.assertIn("[SERVICE]", prompt)
        self.assertIn("[SCHEMA]", prompt)
        self.assertIn("[TEST]", prompt)

    def test_top_ranked_route_is_the_first_route_block_in_the_prompt(self):
        _, _, prompt, _ = self._generate("Create POST API for invoice")
        # Both invoice and shipment routes fit the routes budget (2), but
        # invoice must appear *first* since it's the higher-relevance match.
        invoice_pos = prompt.index("invoice_router.py")
        shipment_pos = prompt.index("shipment_router.py")
        self.assertLess(invoice_pos, shipment_pos)

    def test_context_budget_is_respected_end_to_end(self):
        engine, _, _, _ = self._generate("Create POST API for invoice")
        ctx = engine._last_retrieved_context
        from archapi.indexing.context_retriever import DEFAULT_BUDGET
        self.assertLessEqual(len(ctx.routes), DEFAULT_BUDGET.routes)
        self.assertLessEqual(len(ctx.services), DEFAULT_BUDGET.services)
        self.assertLessEqual(len(ctx.schemas), DEFAULT_BUDGET.schemas)
        self.assertLessEqual(len(ctx.models), DEFAULT_BUDGET.models)
        self.assertLessEqual(len(ctx.tests), DEFAULT_BUDGET.tests)
        self.assertLessEqual(ctx.total_snippet_chars(), DEFAULT_BUDGET.global_char_budget)

    def test_retrieval_is_deterministic(self):
        engine1, _, _, _ = self._generate("Create POST API for invoice")
        engine2, _, _, _ = self._generate("Create POST API for invoice")

        paths1 = [(i.path, i.score) for i in engine1._last_retrieved_context.all_items()]
        paths2 = [(i.path, i.score) for i in engine2._last_retrieved_context.all_items()]
        self.assertEqual(paths1, paths2)


class TestRequestChangesRetrieval(unittest.TestCase):
    """
    The core generalization proof: same repository, only the request text
    changes, and the selected examples change with it -- without touching
    repository contents between calls.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_billing_project(Path(self._tmp.name))

    def _generate(self, request: str):
        provider = _mock_provider()
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        engine.generate_api(request, dry_run=True)
        prompt = provider.complete.call_args[0][0]
        return engine, prompt

    def test_top_route_switches_with_the_request(self):
        _, invoice_prompt = self._generate("Create POST API for invoice")
        _, shipment_prompt = self._generate("Create POST API for shipment")

        # Both files can appear in either prompt (routes budget is 2), but
        # which one leads must track the request.
        self.assertLess(
            invoice_prompt.index("invoice_router.py"),
            invoice_prompt.index("shipment_router.py"),
        )
        self.assertLess(
            shipment_prompt.index("shipment_router.py"),
            shipment_prompt.index("invoice_router.py"),
        )

    def test_single_slot_model_category_flips_with_the_request(self):
        # models budget is 1, so this is an unambiguous single-item switch.
        invoice_engine, invoice_prompt = self._generate("Create POST API for invoice")
        shipment_engine, shipment_prompt = self._generate("Create POST API for shipment")

        self.assertEqual(
            invoice_engine._last_retrieved_context.models[0].path,
            "app/models/invoice_model.py",
        )
        self.assertEqual(
            shipment_engine._last_retrieved_context.models[0].path,
            "app/models/shipment_model.py",
        )
        self.assertIn("invoice_model.py", invoice_prompt)
        self.assertNotIn("shipment_model.py", invoice_prompt)
        self.assertIn("shipment_model.py", shipment_prompt)
        self.assertNotIn("invoice_model.py", shipment_prompt)


class TestSecurityBoundaryThroughRetrieval(unittest.TestCase):
    """
    The critical security proof: a secret embedded in the file the
    retriever actually selects must still be stripped before it reaches the
    (fake) provider -- not merely absent because it was never selected.
    """

    def test_secret_in_retrieved_file_is_redacted_before_transmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_billing_project(Path(tmp))
            (project / "app/routers/invoice_router.py").write_text(
                "from fastapi import APIRouter\n\n"
                'SOME_API_KEY = "not_a_real_secret_placeholder_value"\n\n'
                "router = APIRouter()\n\n"
                '@router.post("/invoices")\n'
                "async def create_invoice():\n"
                "    return {}\n"
            )

            provider = _mock_provider()
            engine = ArchAPI(str(project), use_llm=True, llm_provider=provider)
            engine.generate_api("Create POST API for invoice", dry_run=True)

            # Prove retrieval actually selected the file containing the
            # secret (not that it was skipped and the test is vacuous).
            ctx = engine._last_retrieved_context
            selected_paths = {item.path for item in ctx.all_items()}
            self.assertIn("app/routers/invoice_router.py", selected_paths)
            route_item = next(
                i for i in ctx.all_items() if i.path == "app/routers/invoice_router.py"
            )
            self.assertIn("not_a_real_secret_placeholder_value", route_item.snippet)

            sent_prompt = provider.complete.call_args[0][0]
            self.assertNotIn("not_a_real_secret_placeholder_value", sent_prompt)
            self.assertIn("REDACTED", sent_prompt)


class TestPhase6RegressionThroughRetrieval(unittest.TestCase):
    """
    Lightweight, self-contained re-proof (independent of test_archapi_suite)
    that Phase 6 enforcement and the deterministic path are untouched by the
    7E integration.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_billing_project(Path(self._tmp.name))

    def test_llm_response_still_parses_correctly(self):
        provider = _mock_provider()
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api("Create POST API for invoice", dry_run=True)

        self.assertEqual(result.plan.method, "POST")
        provider.complete.assert_called_once()

    def test_policy_gate_still_blocks_bootstrap_files(self):
        provider = _mock_provider(response_files=[
            {"path": "app/main.py", "content": "app = FastAPI()\n"}
        ])
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api("Create POST API for invoice", dry_run=True)

        self.assertFalse(result.validation_report.success)
        self.assertTrue(any("bootstrap" in err for err in result.validation_report.errors))

    def test_framework_validation_still_runs(self):
        # Missing required FastAPI layers (_service.py / _schema.py) should
        # still be caught by FastAPIAdapter.validate_generated_code.
        provider = _mock_provider(response_files=[
            {"path": "app/routers/incomplete_router.py", "content": "x = 1\n"}
        ])
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api("Create POST API for invoice", dry_run=True)

        self.assertFalse(result.validation_report.success)
        self.assertTrue(any("Missing generated FastAPI layer" in err for err in result.validation_report.errors))

    def test_dry_run_true_performs_no_writes(self):
        provider = _mock_provider(response_files=[
            {"path": "app/routers/new_thing_router.py", "content": "x = 1\n"},
            {"path": "app/services/new_thing_service.py", "content": "x = 1\n"},
            {"path": "app/schemas/new_thing_schema.py", "content": "x = 1\n"},
            {"path": "tests/test_new_thing.py", "content": "x = 1\n"},
        ])
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        engine.generate_api("Create POST API for invoice", dry_run=True)

        self.assertFalse((self.project / "app/routers/new_thing_router.py").exists())

    def test_use_llm_false_path_is_unaffected(self):
        engine = ArchAPI(str(self.project), use_llm=False)
        result = engine.generate_api("Create POST API for invoice", dry_run=True)

        self.assertTrue(result.validation_report.success, result.validation_report.errors)
        self.assertIsNone(engine._last_retrieved_context)


if __name__ == "__main__":
    unittest.main()
