import tempfile
import unittest
from pathlib import Path

from archapi.frameworks.generic import GenericAdapter
from archapi.indexing.context_retriever import (
    ContextBudget,
    ContextRetriever,
    RetrievedContext,
)
from archapi.indexing.repository_index import RepositoryIndex, build_repository_index
from archapi.indexing.relevance_scorer import RelevanceScorer
from archapi.planning.intent_planner import IntentPlanner
from archapi.types import APIPlan

_DEFAULT_LAYERS = ["route", "controller", "service", "schema", "test"]
_CATEGORIES = (
    "routes", "controllers", "services", "schemas", "models",
    "auth_patterns", "validation_patterns", "tests",
)


def build_plan(request: str) -> APIPlan:
    intent = IntentPlanner().plan(request)
    return APIPlan(
        request=request,
        method=intent.method,
        path=intent.path,
        entities=intent.entities,
        layers=_DEFAULT_LAYERS,
        generation_allowed=True,
    )


# ===========================================================================
# A deliberately noisy fixture: 5 routes, 3 controllers, 4 services,
# 2 schemas, 2 models, 1 auth middleware, 3 tests -- only "refund" is the
# requested resource. This is large enough that a naive "take the globally
# highest-scoring N files" strategy visibly under-represents some
# categories (see TestNaiveTopNComparison below) compared to
# ContextRetriever's per-category budget.
# ===========================================================================

def create_noisy_commerce_project(root: Path) -> Path:
    project = root / "sample_noisy_commerce_api"

    for rel_dir in (
        "src/routes", "src/controllers", "src/services",
        "src/schemas", "src/models", "src/middleware", "tests",
    ):
        (project / rel_dir).mkdir(parents=True, exist_ok=True)

    (project / "src/routes/refund.routes.ts").write_text(
        'import { Router } from "express";\n'
        'import { refundController } from "../controllers/refund.controller";\n'
        'import { requireAuth } from "../middleware/auth.middleware";\n\n'
        "const router = Router();\n"
        'router.post("/refunds", requireAuth, refundController.handle);\n'
        "export default router;\n"
    )
    (project / "src/routes/order.routes.ts").write_text(
        'router.post("/orders", orderController.handle);\n'
    )
    (project / "src/routes/user.routes.ts").write_text(
        'router.get("/users/:id", userController.handle);\n'
    )
    (project / "src/routes/product.routes.ts").write_text(
        'router.get("/products/:id", productController.handle);\n'
    )
    (project / "src/routes/inventory.routes.ts").write_text(
        'router.get("/inventory/:id", inventoryController.handle);\n'
    )

    (project / "src/controllers/refund.controller.ts").write_text(
        "export const refundController = { async handle(req, res) { return res.json({}); } };\n"
    )
    (project / "src/controllers/order.controller.ts").write_text(
        "export const orderController = { async handle(req, res) { return res.json({}); } };\n"
    )
    (project / "src/controllers/user.controller.ts").write_text(
        "export const userController = { async handle(req, res) { return res.json({}); } };\n"
    )

    (project / "src/services/refund.service.ts").write_text(
        'import { refundSchema } from "../schemas/refund.schema";\n\n'
        "export const refundService = {\n"
        "  async execute(payload) {\n"
        "    const parsed = refundSchema.parse(payload);\n"
        "    return { ok: true, parsed };\n"
        "  },\n"
        "};\n"
    )
    (project / "src/services/order.service.ts").write_text(
        "export const orderService = { async execute() { return {}; } };\n"
    )
    (project / "src/services/user.service.ts").write_text(
        "export const userService = { async execute() { return {}; } };\n"
    )
    (project / "src/services/product.service.ts").write_text(
        "export const productService = { async execute() { return {}; } };\n"
    )

    (project / "src/schemas/refund.schema.ts").write_text(
        'import { z } from "zod";\n\n'
        "export const refundSchema = z.object({ orderId: z.string(), amount: z.number() });\n"
    )
    (project / "src/schemas/order.schema.ts").write_text(
        'import { z } from "zod";\n\nexport const orderSchema = z.object({ id: z.string() });\n'
    )

    (project / "src/models/refund.model.ts").write_text("export interface Refund { id: string; }\n")
    (project / "src/models/order.model.ts").write_text("export interface Order { id: string; }\n")

    (project / "src/middleware/auth.middleware.ts").write_text(
        "export function requireAuth(req, res, next) {\n  next();\n}\n"
    )

    (project / "tests/refund.spec.ts").write_text(
        "describe('refund', () => { it('works', () => expect(true).toBe(true)); });\n"
    )
    (project / "tests/order.spec.ts").write_text(
        "describe('order', () => { it('works', () => expect(true).toBe(true)); });\n"
    )
    (project / "tests/user.spec.ts").write_text(
        "describe('user', () => { it('works', () => expect(true).toBe(true)); });\n"
    )

    return project


class ContextRetrieverTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_noisy_commerce_project(Path(self._tmp.name))
        self.scan = GenericAdapter().scan(self.project)
        self.index = build_repository_index(self.scan, genome=None)
        self.request = "Create authenticated POST API for refund request with validation"
        self.plan = build_plan(self.request)


class TestContextRetrieverCrossSection(ContextRetrieverTestBase):
    def test_retrieves_a_balanced_refund_cross_section(self):
        ctx = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)

        self.assertEqual(ctx.routes[0].path, "src/routes/refund.routes.ts")
        self.assertEqual(ctx.controllers[0].path, "src/controllers/refund.controller.ts")
        self.assertEqual(ctx.services[0].path, "src/services/refund.service.ts")
        self.assertEqual(ctx.schemas[0].path, "src/schemas/refund.schema.ts")
        self.assertEqual(ctx.models[0].path, "src/models/refund.model.ts")
        self.assertEqual(ctx.tests[0].path, "tests/refund.spec.ts")

        self.assertTrue(ctx.auth_patterns)
        self.assertTrue(ctx.validation_patterns)

        for category in _CATEGORIES:
            self.assertTrue(getattr(ctx, category), f"{category} should not be empty")

    def test_per_category_limits_are_respected(self):
        ctx = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)
        budget = ContextRetriever().budget

        self.assertLessEqual(len(ctx.routes), budget.routes)
        self.assertLessEqual(len(ctx.controllers), budget.controllers)
        self.assertLessEqual(len(ctx.services), budget.services)
        self.assertLessEqual(len(ctx.schemas), budget.schemas)
        self.assertLessEqual(len(ctx.models), budget.models)
        self.assertLessEqual(len(ctx.tests), budget.tests)
        self.assertLessEqual(len(ctx.auth_patterns), budget.auth_patterns)
        self.assertLessEqual(len(ctx.validation_patterns), budget.validation_patterns)

    def test_irrelevant_zero_score_candidate_is_excluded(self):
        ctx = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)
        # order.model.ts scores 0 (no entity/layer-in-plan-layers/method/etc.
        # signal at all -- "model" isn't in the default requested layers)
        # and must never surface anywhere in the result.
        paths = {item.path for item in ctx.all_items()}
        self.assertNotIn("src/models/order.model.ts", paths)


class TestContextRetrieverDeduplication(ContextRetrieverTestBase):
    def test_duplicate_across_categories_collapses_in_all_items(self):
        ctx = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)

        # refund.routes.ts legitimately carries both a route signal and an
        # auth signal (it imports/uses requireAuth directly).
        self.assertIn("src/routes/refund.routes.ts", {i.path for i in ctx.routes})
        self.assertIn("src/routes/refund.routes.ts", {i.path for i in ctx.auth_patterns})

        occurrences = [item.path for item in ctx.all_items()].count("src/routes/refund.routes.ts")
        self.assertEqual(occurrences, 1)

    def test_all_items_has_no_duplicate_paths(self):
        ctx = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)
        paths = [item.path for item in ctx.all_items()]
        self.assertEqual(len(paths), len(set(paths)))


class TestContextRetrieverAuthValidationGating(ContextRetrieverTestBase):
    def test_auth_context_appears_only_when_requested(self):
        with_auth = ContextRetriever().retrieve(
            request="Create authenticated POST API for refund request",
            plan=build_plan("Create authenticated POST API for refund request"),
            index=self.index,
        )
        without_auth = ContextRetriever().retrieve(
            request="Create POST API for refund request",
            plan=build_plan("Create POST API for refund request"),
            index=self.index,
        )

        self.assertTrue(with_auth.auth_patterns)
        self.assertEqual(without_auth.auth_patterns, [])

        # Not requesting auth must not otherwise change route selection.
        self.assertEqual(
            [i.path for i in with_auth.routes], [i.path for i in without_auth.routes]
        )

    def test_validation_context_appears_only_when_requested(self):
        with_validation = ContextRetriever().retrieve(
            request="Create authenticated POST API for refund request with validation",
            plan=build_plan("Create authenticated POST API for refund request with validation"),
            index=self.index,
        )
        without_validation = ContextRetriever().retrieve(
            request="Create authenticated POST API for refund request",
            plan=build_plan("Create authenticated POST API for refund request"),
            index=self.index,
        )

        self.assertTrue(with_validation.validation_patterns)
        self.assertEqual(without_validation.validation_patterns, [])


class TestContextRetrieverBudget(ContextRetrieverTestBase):
    def test_global_char_budget_is_enforced(self):
        tiny_budget = ContextBudget(global_char_budget=250)
        ctx = ContextRetriever(budget=tiny_budget).retrieve(
            request=self.request, plan=self.plan, index=self.index
        )
        self.assertLessEqual(ctx.total_snippet_chars(), 250)
        self.assertGreater(len(ctx.all_items()), 0)  # still usable, not wiped out

    def test_zero_count_budget_produces_empty_context(self):
        empty_budget = ContextBudget(
            routes=0, controllers=0, services=0, schemas=0, models=0,
            tests=0, auth_patterns=0, validation_patterns=0,
        )
        ctx = ContextRetriever(budget=empty_budget).retrieve(
            request=self.request, plan=self.plan, index=self.index
        )
        self.assertEqual(ctx, RetrievedContext())

    def test_vanishingly_small_char_budget_degrades_gracefully(self):
        tiny_budget = ContextBudget(global_char_budget=1)
        ctx = ContextRetriever(budget=tiny_budget).retrieve(
            request=self.request, plan=self.plan, index=self.index
        )
        # No snippet is small enough to fit -- empty, but no exception.
        self.assertEqual(ctx.all_items(), [])

    def test_budget_monotonicity_never_removes_a_previously_selected_item(self):
        tight = ContextRetriever(budget=ContextBudget(global_char_budget=250)).retrieve(
            request=self.request, plan=self.plan, index=self.index
        )
        generous = ContextRetriever(budget=ContextBudget(global_char_budget=12_000)).retrieve(
            request=self.request, plan=self.plan, index=self.index
        )

        tight_paths = {item.path for item in tight.all_items()}
        generous_paths = {item.path for item in generous.all_items()}

        self.assertTrue(tight_paths)  # sanity: the tight budget actually excluded something
        self.assertTrue(tight_paths.issubset(generous_paths))
        self.assertLess(len(tight_paths), len(generous_paths))


class TestContextRetrieverDeterminism(ContextRetrieverTestBase):
    def test_repeated_retrieval_is_identical(self):
        first = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)
        second = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)
        self.assertEqual(first, second)

    def test_scores_and_reasons_survive_retrieval_unchanged(self):
        ctx = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)
        scored_by_path = {
            str(s.unit.path): s for s in RelevanceScorer().score(self.plan, self.index)
        }

        for item in ctx.all_items():
            reference = scored_by_path[item.path]
            self.assertEqual(item.score, reference.score)
            self.assertEqual(item.reasons, reference.reasons)


class TestNaiveTopNComparison(ContextRetrieverTestBase):
    def test_layer_aware_budget_beats_naive_global_topn(self):
        """
        The core 7D claim: a naive "take the N globally highest-scoring
        files" strategy under-represents categories that ContextRetriever's
        per-category budget guarantees. Concretely, in this fixture there
        are three "test" candidates that all tie at the same score once
        order/user diverge from refund -- but eight *other* candidates
        (controllers/routes/services) share that identical tied score and
        sort ahead of them alphabetically by layer. A naive top-N (sized to
        match what ContextRetriever actually selects) therefore surfaces
        only one test file, while ContextRetriever's dedicated test budget
        still secures two.
        """
        ctx = ContextRetriever().retrieve(request=self.request, plan=self.plan, index=self.index)
        scored = RelevanceScorer().score(self.plan, self.index)

        naive_topn = scored[: len(ctx.all_items())]
        naive_test_count = sum(1 for s in naive_topn if s.unit.layer == "test")

        self.assertEqual(naive_test_count, 1)
        self.assertEqual(len(ctx.tests), 2)
        self.assertGreater(len(ctx.tests), naive_test_count)


class TestContextRetrieverSparseRepositories(unittest.TestCase):
    def test_empty_index_does_not_raise(self):
        empty_index = RepositoryIndex(units=[])
        plan = build_plan("Create POST API for refund request")

        ctx = ContextRetriever().retrieve(request=plan.request, plan=plan, index=empty_index)

        self.assertEqual(ctx, RetrievedContext())

    def test_sparse_repository_with_no_recognized_layers_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "sparse_project"
            project.mkdir(parents=True)
            # Not classified into any of route/controller/service/schema/
            # model/middleware/test, so build_repository_index indexes
            # nothing at all -- the retriever must still return cleanly.
            (project / "README.md").write_text("# Sparse project\n")

            scan = GenericAdapter().scan(project)
            index = build_repository_index(scan, genome=None)
            plan = build_plan("Create authenticated POST API for refund request with validation")

            ctx = ContextRetriever().retrieve(request=plan.request, plan=plan, index=index)

            self.assertEqual(ctx, RetrievedContext())

    def test_sparse_repository_with_one_unrelated_route_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "sparse_project"
            (project / "src/routes").mkdir(parents=True)
            (project / "src/routes/health.routes.ts").write_text(
                'router.get("/health", healthController.handle);\n'
            )

            scan = GenericAdapter().scan(project)
            index = build_repository_index(scan, genome=None)
            plan = build_plan("Create authenticated POST API for refund request with validation")

            ctx = ContextRetriever().retrieve(request=plan.request, plan=plan, index=index)

            # No entity/method/auth/validation signal matches this file, but
            # it still earns the baseline "plausible route" layer-match
            # score -- the only candidate available, so it's what surfaces.
            self.assertEqual(len(ctx.all_items()), 1)
            self.assertEqual(ctx.routes[0].path, "src/routes/health.routes.ts")
            self.assertEqual(ctx.services, [])
            self.assertEqual(ctx.auth_patterns, [])


if __name__ == "__main__":
    unittest.main()
