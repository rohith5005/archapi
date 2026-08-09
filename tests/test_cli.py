import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from archapi import cli
from tests.test_archapi_suite import create_fastapi_project


def run_cli(argv):
    """Invoke archapi.cli.main() in-process and capture (exit_code, stdout, stderr)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = cli.main(argv)
        except SystemExit as exc:  # argparse's own usage errors call sys.exit()
            code = exc.code if isinstance(exc.code, int) else 2
    return code, stdout.getvalue(), stderr.getvalue()


def _snapshot(project: Path):
    return sorted(
        str(p.relative_to(project)) for p in project.rglob("*") if p.is_file()
    )


class CliTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_fastapi_project(Path(self._tmp.name))


class TestHelpAndBasicCommands(CliTestBase):
    def test_help_exits_zero(self):
        code, out, _ = run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("archapi", out)

    def test_scan_human_output(self):
        code, out, _ = run_cli(["scan", str(self.project)])
        self.assertEqual(code, 0)
        self.assertIn("Framework: fastapi", out)
        self.assertIn("Routes:", out)

    def test_scan_json_output_is_valid_json(self):
        code, out, _ = run_cli(["scan", str(self.project), "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["framework"], "fastapi")
        self.assertIn("routes", data)

    def test_detect_human_output(self):
        code, out, _ = run_cli(["detect", str(self.project)])
        self.assertEqual(code, 0)
        self.assertIn("Framework: fastapi", out)

    def test_plan_is_read_only_and_json_valid(self):
        before = _snapshot(self.project)
        code, out, _ = run_cli(["plan", str(self.project), "Create GET API for invoice", "--json"])
        after = _snapshot(self.project)

        self.assertEqual(code, 0)
        self.assertEqual(before, after)
        data = json.loads(out)
        self.assertEqual(data["method"], "GET")
        self.assertIn("Invoice", data["entities"])


class TestGenerateDryRunSafety(CliTestBase):
    def test_generate_defaults_to_dry_run_no_writes(self):
        before = _snapshot(self.project)
        code, out, _ = run_cli(["generate", str(self.project), "Create GET API for invoice"])
        after = _snapshot(self.project)

        self.assertEqual(code, 0)
        self.assertEqual(before, after)
        self.assertIn("Dry run", out)

    def test_generate_apply_actually_writes(self):
        before = _snapshot(self.project)
        code, _, _ = run_cli(["generate", str(self.project), "Create GET API for invoice", "--apply"])
        after = _snapshot(self.project)

        self.assertEqual(code, 0)
        self.assertGreater(len(after), len(before))
        self.assertTrue((self.project / "app/routers/invoice_router.py").exists())

    def test_generate_json_output_structure(self):
        code, out, _ = run_cli(["generate", str(self.project), "Create GET API for invoice", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["mode"], "deterministic")
        self.assertTrue(data["dry_run"])
        self.assertIn("generated_paths", data)
        self.assertIn("policy_gate_pass", data)
        self.assertIn("framework_validation_pass", data)

    def test_use_llm_defaults_off(self):
        code, out, _ = run_cli(["generate", str(self.project), "Create GET API for invoice", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["mode"], "deterministic")


class TestExitCodes(CliTestBase):
    def test_success_exits_zero(self):
        code, _, _ = run_cli(["generate", str(self.project), "Create GET API for invoice"])
        self.assertEqual(code, cli.EXIT_OK)

    def test_missing_required_arg_exits_invalid_usage(self):
        code, _, _ = run_cli(["generate"])
        self.assertEqual(code, cli.EXIT_INVALID_USAGE)

    def test_unknown_flag_exits_invalid_usage(self):
        code, _, _ = run_cli(["generate", str(self.project), "x", "--skip-safety"])
        self.assertEqual(code, cli.EXIT_INVALID_USAGE)

    def test_nonexistent_project_path_exits_invalid_usage(self):
        code, _, err = run_cli(["scan", "/definitely/does/not/exist/xyz"])
        self.assertEqual(code, cli.EXIT_INVALID_USAGE)
        self.assertIn("does not exist", err)

    def test_llm_without_api_key_exits_provider_failure(self):
        with patch.dict("os.environ", {}, clear=True):
            code, _, err = run_cli(
                ["generate", str(self.project), "Create GET API for invoice", "--llm"]
            )
        self.assertEqual(code, cli.EXIT_PROVIDER_FAILURE)
        self.assertIn("provider error", err)

    def test_unknown_provider_config_exits_invalid_usage(self):
        with patch.dict("os.environ", {"ARCHAPI_LLM_PROVIDER": "not-real"}, clear=False):
            code, _, err = run_cli(
                ["generate", str(self.project), "Create GET API for invoice", "--llm"]
            )
        self.assertEqual(code, cli.EXIT_INVALID_USAGE)
        self.assertIn("configuration error", err)

    def test_invalid_project_config_file_exits_invalid_usage(self):
        (self.project / "archapi.toml").write_text("[archapi\nbroken\n")
        code, _, err = run_cli(["scan", str(self.project)])
        self.assertEqual(code, cli.EXIT_INVALID_USAGE)


class TestDebugFlag(CliTestBase):
    def test_debug_shows_more_than_default_on_unexpected_error(self):
        with patch.dict("os.environ", {}, clear=True):
            _, _, err_default = run_cli(
                ["generate", str(self.project), "Create GET API for invoice", "--llm"]
            )
            code, _, err_debug = run_cli(
                ["--debug", "generate", str(self.project), "Create GET API for invoice", "--llm"]
            )
        self.assertEqual(code, cli.EXIT_PROVIDER_FAILURE)
        self.assertGreater(len(err_debug), len(err_default))
        self.assertIn("Traceback", err_debug)
        self.assertNotIn("Traceback", err_default)


class TestNoDangerousFlags(CliTestBase):
    def test_no_skip_safety_style_flags_exist(self):
        for flag in ("--skip-safety", "--disable-policy-gate", "--force-unsafe", "--no-validate"):
            with self.subTest(flag=flag):
                code, _, _ = run_cli(
                    ["generate", str(self.project), "Create GET API for invoice", flag]
                )
                self.assertEqual(code, cli.EXIT_INVALID_USAGE)


class TestSecretsNeverExposed(CliTestBase):
    def test_api_key_never_appears_in_json_output(self):
        fake_key = "sk-should-never-appear-in-output-abc123"
        fake_response = json.dumps({
            "method": "GET", "path": "/invoices/{id}", "entities": ["invoice"],
            "layers": ["route", "service", "schema", "test"],
            "files": [
                {"path": "app/routers/invoice_router.py", "content": "x = 1\n"},
                {"path": "app/services/invoice_service.py", "content": "x = 1\n"},
                {"path": "app/schemas/invoice_schema.py", "content": "x = 1\n"},
                {"path": "tests/test_invoice.py", "content": "def test_x(): assert True\n"},
            ],
        })
        with patch.dict("os.environ", {"OPENAI_API_KEY": fake_key}, clear=False):
            with patch(
                "archapi.llm.openai_provider.OpenAIProvider.complete",
                return_value=fake_response,
            ):
                code, out, err = run_cli(
                    ["generate", str(self.project), "Create GET API for invoice", "--llm", "--json"]
                )
        self.assertEqual(code, cli.EXIT_OK)
        self.assertNotIn(fake_key, out)
        self.assertNotIn(fake_key, err)

    def test_api_key_never_appears_in_human_output(self):
        fake_key = "sk-should-never-appear-in-human-output-xyz789"
        fake_response = json.dumps({
            "method": "GET", "path": "/invoices/{id}", "entities": ["invoice"],
            "layers": ["route", "service", "schema", "test"],
            "files": [
                {"path": "app/routers/invoice_router.py", "content": "x = 1\n"},
                {"path": "app/services/invoice_service.py", "content": "x = 1\n"},
                {"path": "app/schemas/invoice_schema.py", "content": "x = 1\n"},
                {"path": "tests/test_invoice.py", "content": "def test_x(): assert True\n"},
            ],
        })
        with patch.dict("os.environ", {"OPENAI_API_KEY": fake_key}, clear=False):
            with patch(
                "archapi.llm.openai_provider.OpenAIProvider.complete",
                return_value=fake_response,
            ):
                code, out, err = run_cli(
                    ["generate", str(self.project), "Create GET API for invoice", "--llm"]
                )
        self.assertEqual(code, cli.EXIT_OK)
        self.assertNotIn(fake_key, out)
        self.assertNotIn(fake_key, err)


class TestBlockedGenerationCannotBeApplied(CliTestBase):
    def test_blocked_policy_gate_result_is_not_written_even_with_apply(self):
        # Bootstrap-file response -- PolicyGate must block this.
        fake_response = json.dumps({
            "method": "GET", "path": "/x", "entities": ["x"], "layers": ["route"],
            "files": [{"path": "app/main.py", "content": "app = FastAPI()\n"}],
        })
        before = _snapshot(self.project)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake-for-test"}, clear=False):
            with patch(
                "archapi.llm.openai_provider.OpenAIProvider.complete",
                return_value=fake_response,
            ):
                code, out, _ = run_cli(
                    ["generate", str(self.project), "Create GET API", "--llm", "--apply"]
                )
        after = _snapshot(self.project)

        self.assertEqual(code, cli.EXIT_REJECTED)
        self.assertEqual(before, after)  # nothing written despite --apply
        self.assertIn("Blocked", out)

    def test_path_traversal_result_is_not_written_even_with_apply(self):
        fake_response = json.dumps({
            "method": "GET", "path": "/x", "entities": ["x"], "layers": ["route"],
            "files": [{"path": "../outside_the_project.py", "content": "x = 1\n"}],
        })
        before = _snapshot(self.project)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake-for-test"}, clear=False):
            with patch(
                "archapi.llm.openai_provider.OpenAIProvider.complete",
                return_value=fake_response,
            ):
                code, _, _ = run_cli(
                    ["generate", str(self.project), "Create GET API", "--llm", "--apply"]
                )
        after = _snapshot(self.project)

        self.assertEqual(code, cli.EXIT_REJECTED)
        self.assertEqual(before, after)
        self.assertFalse((self.project.parent / "outside_the_project.py").exists())


if __name__ == "__main__":
    unittest.main()
