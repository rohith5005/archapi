"""
Phase 8B: tests for the evaluation harness itself (evaluation/), not for
ArchAPI's generation quality -- that's what evaluation/ is for measuring,
not what these tests are for proving. Every test here uses
provider_mode="deterministic" (the default); none may use "real_llm".
"""

import dataclasses
import json
import unittest
from unittest.mock import patch

from evaluation.cases import CASES, get_case
from evaluation.metrics import EvaluationResult
from evaluation.runner import run_case, run_comparison

_FASTAPI_CASE = get_case("fastapi_shipment_status")
_DJANGO_CASE = get_case("django_invoice")
_EXPRESS_CASE = get_case("express_warranty_claim")


class TestDeterminism(unittest.TestCase):
    def test_same_case_same_metrics_across_runs(self):
        first = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")
        second = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")
        self.assertEqual(first.to_dict(), second.to_dict())


class TestBaselineVsRetrieval(unittest.TestCase):
    def test_comparison_holds_request_and_framework_constant(self):
        baseline, retrieval = run_comparison(_FASTAPI_CASE)
        self.assertEqual(baseline.request, retrieval.request)
        self.assertEqual(baseline.framework, retrieval.framework)
        self.assertEqual(baseline.request, _FASTAPI_CASE.request)
        self.assertEqual(baseline.mode, "baseline")
        self.assertEqual(retrieval.mode, "archapi_retrieval")

    def test_retrieval_mode_records_retrieved_paths(self):
        _, retrieval = run_comparison(_DJANGO_CASE)
        self.assertTrue(retrieval.retrieved_paths)

    def test_baseline_mode_does_not_pretend_retrieval_occurred(self):
        baseline, _ = run_comparison(_DJANGO_CASE)
        self.assertEqual(baseline.retrieved_paths, [])


class TestValidationAndScoringPropagation(unittest.TestCase):
    def test_framework_validation_and_policy_results_propagate(self):
        # The runner's fake provider produces a framework-conformant
        # response for each case's own framework -- this should pass both
        # gates cleanly under the deterministic (free) provider.
        result = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")
        self.assertTrue(result.parse_success)
        self.assertTrue(result.framework_validation_pass, result.errors)
        self.assertTrue(result.policy_gate_pass, result.errors)
        self.assertTrue(result.generation_allowed)
        self.assertEqual(result.errors, [])

    def test_django_flat_tests_py_convention_passes_thanks_to_8a(self):
        # The runner's Django fake response deliberately uses the flat
        # {app}/tests.py convention -- proves the Phase 8A fix is live
        # inside the harness's own default fake provider, not just in
        # test_validator_repository_consistency.py.
        result = run_case(_DJANGO_CASE, context_mode="archapi_retrieval")
        self.assertTrue(any(p.endswith("/tests.py") for p in result.generated_paths))
        self.assertTrue(result.framework_validation_pass, result.errors)

    def test_architecture_score_is_populated(self):
        result = run_case(_EXPRESS_CASE, context_mode="archapi_retrieval")
        self.assertIsNotNone(result.architecture_score)
        self.assertIsInstance(result.architecture_score, float)

    def test_expected_and_generated_layers_are_recorded(self):
        result = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")
        self.assertEqual(set(result.expected_layers), {"route", "service", "schema", "test"})
        self.assertTrue(set(result.expected_layers).issubset(set(result.generated_layers)))


class TestFailurePathsStillProduceAResult(unittest.TestCase):
    def test_missing_layer_produces_errors_and_failing_result_not_an_exception(self):
        from evaluation import runner as runner_module

        def _bad_response(_case):
            from unittest.mock import MagicMock
            provider = MagicMock()
            provider.complete.return_value = json.dumps({
                "method": "POST", "path": "/x", "entities": ["x"],
                "layers": ["route"],
                "files": [{"path": "app/routers/incomplete_router.py", "content": "x = 1\n"}],
            })
            return provider

        with patch.object(runner_module, "_fake_provider", _bad_response):
            result = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")

        self.assertTrue(result.parse_success)
        self.assertFalse(result.framework_validation_pass)
        self.assertFalse(result.generation_allowed)
        self.assertTrue(result.errors)

    def test_provider_error_produces_a_result_with_errors_not_a_crash(self):
        from evaluation import runner as runner_module
        from archapi.llm.errors import LLMProviderError
        from unittest.mock import MagicMock

        def _erroring_provider(_case):
            provider = MagicMock()
            provider.complete.side_effect = LLMProviderError("simulated outage")
            return provider

        with patch.object(runner_module, "_fake_provider", _erroring_provider):
            result = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")

        self.assertFalse(result.parse_success)
        self.assertFalse(result.generation_allowed)
        self.assertTrue(any("provider error" in e for e in result.errors))

    def test_parse_error_produces_a_result_with_errors_not_a_crash(self):
        from evaluation import runner as runner_module
        from unittest.mock import MagicMock

        def _unparsable_provider(_case):
            provider = MagicMock()
            provider.complete.return_value = "not valid json at all"
            return provider

        with patch.object(runner_module, "_fake_provider", _unparsable_provider):
            result = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")

        self.assertFalse(result.parse_success)
        self.assertTrue(any("parse error" in e for e in result.errors))


class TestSerialization(unittest.TestCase):
    def test_result_round_trips_through_json(self):
        result = run_case(_DJANGO_CASE, context_mode="archapi_retrieval")

        blob = json.dumps(result.to_dict())
        restored = EvaluationResult.from_dict(json.loads(blob))

        self.assertEqual(result.to_dict(), restored.to_dict())

    def test_no_secret_bearing_fields_in_the_schema(self):
        field_names = {f.name for f in dataclasses.fields(EvaluationResult)}
        disallowed_substrings = ("api_key", "apikey", "secret", "token", "prompt", "snippet", "environ")
        for name in field_names:
            for banned in disallowed_substrings:
                self.assertNotIn(
                    banned, name.lower(),
                    f"EvaluationResult field {name!r} looks like it could hold secret-bearing content",
                )

    def test_serialized_result_contains_no_api_key_value(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-should-never-appear-anywhere"}):
            result = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")
            blob = json.dumps(result.to_dict())
        self.assertNotIn("sk-should-never-appear-anywhere", blob)


class TestRealLlmRequiresExplicitOptIn(unittest.TestCase):
    def test_real_llm_without_confirm_raises_before_any_network_attempt(self):
        # No OPENAI_API_KEY needed for this test to be meaningful: the
        # RuntimeError must fire from the confirm_real_call check alone,
        # before OpenAIProvider (which needs the key) is ever constructed.
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                run_case(_FASTAPI_CASE, context_mode="archapi_retrieval", provider_mode="real_llm")
        self.assertIn("confirm_real_call", str(ctx.exception))

    def test_invalid_provider_mode_rejected(self):
        with self.assertRaises(ValueError):
            run_case(_FASTAPI_CASE, context_mode="archapi_retrieval", provider_mode="not_a_real_mode")

    def test_invalid_context_mode_rejected(self):
        with self.assertRaises(ValueError):
            run_case(_FASTAPI_CASE, context_mode="not_a_real_mode")


class TestUnittestCannotAccidentallyInvokeRealProvider(unittest.TestCase):
    def test_deterministic_mode_never_constructs_openai_provider(self):
        with patch(
            "archapi.llm.openai_provider.OpenAIProvider.__init__",
            side_effect=AssertionError("OpenAIProvider must never be constructed in deterministic mode"),
        ):
            result = run_case(_FASTAPI_CASE, context_mode="archapi_retrieval")  # provider_mode defaults to deterministic
        self.assertTrue(result.parse_success)

    def test_no_test_in_this_suite_can_pass_the_real_llm_opt_in(self):
        # provider_mode="real_llm" alone is inert -- run_case still refuses
        # it without the opt-in kwarg set to True (see
        # TestRealLlmRequiresExplicitOptIn above, which relies on exactly
        # that). The one thing that would actually let a real call through
        # is that kwarg set to True, so a structural guarantee that the
        # pattern never appears anywhere in this file -- built via
        # concatenation below so this line can't itself trip the check --
        # is a stronger, unambiguous invariant than pattern-matching
        # provider_mode itself (which legitimately appears above, in tests
        # that verify it's rejected).
        with open(__file__, "r", encoding="utf-8") as f:
            source = f.read()
        kwarg_name = "confirm" + "_real_call"
        opt_in_pattern = kwarg_name + "=" + "True"
        opt_in_pattern_spaced = kwarg_name + " = " + "True"
        self.assertNotIn(opt_in_pattern, source)
        self.assertNotIn(opt_in_pattern_spaced, source)


class TestAllCasesAreRunnable(unittest.TestCase):
    def test_every_registered_case_runs_cleanly_in_both_context_modes(self):
        for case in CASES:
            for context_mode in ("baseline", "archapi_retrieval"):
                with self.subTest(case=case.case_id, context_mode=context_mode):
                    result = run_case(case, context_mode=context_mode)
                    self.assertEqual(result.case_id, case.case_id)
                    self.assertTrue(result.parse_success)


if __name__ == "__main__":
    unittest.main()
