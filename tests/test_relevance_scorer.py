import tempfile
import unittest
from pathlib import Path

from archapi.frameworks.generic import GenericAdapter
from archapi.indexing.repository_index import build_repository_index
from archapi.indexing.relevance_scorer import RelevanceScorer
from archapi.planning.intent_planner import IntentPlanner
from archapi.types import APIPlan

_DEFAULT_LAYERS = ["route", "controller", "service", "schema", "test"]


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


def create_user_order_refund_project(root: Path) -> Path:
    project = root / "sample_commerce_api"

    (project / "src/routes").mkdir(parents=True, exist_ok=True)
    (project / "src/services").mkdir(parents=True, exist_ok=True)
    (project / "src/middleware").mkdir(parents=True, exist_ok=True)
    (project / "src/schemas").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)

    # Routes: refund matches entity + method + path; order matches method
    # only (also POST, different resource); user matches neither -- this is
    # the "unrelated" tier.
    (project / "src/routes/refund.routes.ts").write_text(
        'import { Router } from "express";\n'
        'import { refundController } from "../controllers/refund.controller";\n'
        'import { requireAuth } from "../middleware/auth.middleware";\n\n'
        "const router = Router();\n"
        'router.post("/refunds", requireAuth, refundController.handle);\n'
        "export default router;\n"
    )

    (project / "src/routes/order.routes.ts").write_text(
        'import { Router } from "express";\n'
        'import { orderController } from "../controllers/order.controller";\n\n'
        "const router = Router();\n"
        'router.post("/orders", orderController.handle);\n'
        "export default router;\n"
    )

    (project / "src/routes/user.routes.ts").write_text(
        'import { Router } from "express";\n'
        'import { userController } from "../controllers/user.controller";\n\n'
        "const router = Router();\n"
        'router.get("/users/:id", userController.handle);\n'
        "export default router;\n"
    )

    (project / "src/services/refund.service.ts").write_text(
        'import { refundSchema } from "../schemas/refund.schema";\n\n'
        "export const refundService = {\n"
        "  async execute(payload: unknown) {\n"
        "    const parsed = refundSchema.parse(payload);\n"
        "    return { ok: true, parsed };\n"
        "  },\n"
        "};\n"
    )

    (project / "src/services/order.service.ts").write_text(
        "export const orderService = {\n"
        "  async execute() {\n"
        "    return {};\n"
        "  },\n"
        "};\n"
    )

    (project / "src/services/user.service.ts").write_text(
        "export const userService = {\n"
        "  async execute() {\n"
        "    return {};\n"
        "  },\n"
        "};\n"
    )

    (project / "src/middleware/auth.middleware.ts").write_text(
        "export function requireAuth(req: unknown, res: unknown, next: () => void) {\n"
        "  next();\n"
        "}\n"
    )

    (project / "src/schemas/refund.schema.ts").write_text(
        'import { z } from "zod";\n\n'
        "export const refundSchema = z.object({\n"
        "  orderId: z.string(),\n"
        "  amount: z.number(),\n"
        "});\n"
    )

    (project / "tests/refund.spec.ts").write_text(
        "describe('refund', () => {\n"
        "  it('works', () => expect(true).toBe(true));\n"
        "});\n"
    )

    (project / "tests/user.spec.ts").write_text(
        "describe('user', () => {\n"
        "  it('works', () => expect(true).toBe(true));\n"
        "});\n"
    )

    return project


class TestRelevanceScorerRanking(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_user_order_refund_project(Path(self._tmp.name))
        self.scan = GenericAdapter().scan(self.project)
        self.index = build_repository_index(self.scan, genome=None)
        self.plan = build_plan(
            "Create authenticated POST API for refund request with validation"
        )
        self.scored_by_path = {
            str(s.unit.path): s
            for s in RelevanceScorer().score(self.plan, self.index)
        }

    def test_planner_resolved_refund_as_the_resource(self):
        # Prerequisite sanity check: if this ever regresses, every
        # assertion below becomes meaningless.
        self.assertEqual(self.plan.entities, ["Refund"])
        self.assertEqual(self.plan.method, "POST")
        self.assertEqual(self.plan.path, "/refunds")

    def test_refund_route_outranks_order_and_user_routes(self):
        refund = self.scored_by_path["src/routes/refund.routes.ts"].score
        order = self.scored_by_path["src/routes/order.routes.ts"].score
        user = self.scored_by_path["src/routes/user.routes.ts"].score

        # Three-tier ranking: refund (entity+method+path match) > order
        # (method-only match, different resource) > user (no match at all).
        self.assertGreater(refund, order)
        self.assertGreater(order, user)

    def test_refund_service_outranks_order_and_user_services(self):
        refund = self.scored_by_path["src/services/refund.service.ts"].score
        order = self.scored_by_path["src/services/order.service.ts"].score
        user = self.scored_by_path["src/services/user.service.ts"].score

        self.assertGreater(refund, order)
        self.assertGreater(refund, user)

    def test_refund_test_outranks_unrelated_test(self):
        refund_test = self.scored_by_path["tests/refund.spec.ts"].score
        user_test = self.scored_by_path["tests/user.spec.ts"].score

        self.assertGreater(refund_test, user_test)
        self.assertIn(
            "test relevance: covers matched resource",
            self.scored_by_path["tests/refund.spec.ts"].reasons,
        )

    def test_reasons_are_explainable_for_top_route(self):
        top_route = self.scored_by_path["src/routes/refund.routes.ts"]
        reasons_text = " | ".join(top_route.reasons)

        self.assertIn("resource match", reasons_text)
        self.assertIn("HTTP method match: POST", reasons_text)
        self.assertIn("architectural layer match: route", reasons_text)
        self.assertIn("route path similarity", reasons_text)


class TestRelevanceScorerAuthAndValidationBoost(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_user_order_refund_project(Path(self._tmp.name))
        self.scan = GenericAdapter().scan(self.project)
        self.index = build_repository_index(self.scan, genome=None)

    def _score_for(self, request: str, path: str):
        plan = build_plan(request)
        scored = {str(s.unit.path): s for s in RelevanceScorer().score(plan, self.index)}
        return scored[path]

    def test_auth_example_gets_auth_relevance_boost(self):
        middleware_path = "src/middleware/auth.middleware.ts"

        with_auth = self._score_for(
            "Create authenticated POST API for refund request", middleware_path
        )
        without_auth = self._score_for(
            "Create POST API for refund request", middleware_path
        )

        self.assertGreater(with_auth.score, without_auth.score)
        self.assertIn("authentication pattern match", with_auth.reasons)
        self.assertNotIn("authentication pattern match", without_auth.reasons)

    def test_validation_example_gets_validation_relevance_boost(self):
        schema_path = "src/schemas/refund.schema.ts"

        with_validation = self._score_for(
            "Create authenticated POST API for refund request with validation",
            schema_path,
        )
        without_validation = self._score_for(
            "Create authenticated POST API for refund request", schema_path
        )

        self.assertGreater(with_validation.score, without_validation.score)
        self.assertIn("validation pattern match", with_validation.reasons)
        self.assertNotIn("validation pattern match", without_validation.reasons)


class TestRelevanceScorerDeterminism(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_user_order_refund_project(Path(self._tmp.name))
        self.scan = GenericAdapter().scan(self.project)
        self.index = build_repository_index(self.scan, genome=None)
        self.plan = build_plan(
            "Create authenticated POST API for refund request with validation"
        )

    def test_repeated_scoring_is_identical(self):
        first = RelevanceScorer().score(self.plan, self.index)
        second = RelevanceScorer().score(self.plan, self.index)

        self.assertEqual(first, second)
        self.assertEqual(
            [(s.unit.path, s.score, s.reasons) for s in first],
            [(s.unit.path, s.score, s.reasons) for s in second],
        )

    def test_ranking_is_fully_ordered_with_stable_tiebreak(self):
        scored = RelevanceScorer().score(self.plan, self.index)

        # Non-increasing score sequence.
        scores = [s.score for s in scored]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # order.service.ts and user.service.ts are expected to tie (neither
        # matches "refund" lexically); the tiebreak must be deterministic
        # (alphabetical by path within the same layer/score).
        order_index = next(
            i for i, s in enumerate(scored) if str(s.unit.path) == "src/services/order.service.ts"
        )
        user_index = next(
            i for i, s in enumerate(scored) if str(s.unit.path) == "src/services/user.service.ts"
        )
        order_score = scored[order_index].score
        user_score = scored[user_index].score

        self.assertEqual(order_score, user_score)
        self.assertLess(order_index, user_index)


if __name__ == "__main__":
    unittest.main()
