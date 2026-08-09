"""
Phase 8D.4: failure-path reliability tests.

Targets one question: does a failure ever leave the repository (or the
filesystem generally) partially modified? Every test here asserts on
*filesystem state*, not just on a returned success/failure flag.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from archapi import ArchAPI, cli
from archapi.generation.file_transaction import FileTransaction, FileTransactionError
from archapi.llm.errors import LLMProviderError
from archapi.types import GeneratedFile, GenerationResult, APIPlan, ValidationReport
from tests.test_archapi_suite import create_fastapi_project


def _make_failing_atomic_write(fail_at_call: int):
    """
    Patched onto FileTransaction._atomic_write: raises on exactly the Nth
    call, succeeding normally on every other call -- including calls the
    rollback path itself makes to restore an overwritten file's original
    content. Simulates a realistic transient failure (one write hits an
    I/O hiccup) rather than "every write from now on fails forever," which
    would make rollback's own restoration writes impossible by
    construction and isn't the scenario being tested here.
    """
    original = FileTransaction._atomic_write
    state = {"count": 0}

    def wrapper(self, target, content):
        state["count"] += 1
        if state["count"] == fail_at_call:
            raise OSError("simulated disk failure")
        original(self, target, content)

    return wrapper


def _snapshot(project: Path):
    return sorted(str(p.relative_to(project)) for p in project.rglob("*") if p.is_file())


def _run_cli(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, stdout.getvalue(), stderr.getvalue()


# ===========================================================================
# FileTransaction: rollback mechanics
# ===========================================================================

class TestFileTransactionRollback(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)

    def _files(self):
        return [
            GeneratedFile(Path("a/one.py"), "one\n"),
            GeneratedFile(Path("a/two.py"), "two\n"),
            GeneratedFile(Path("b/three.py"), "three\n"),
        ]

    def test_successful_transaction_writes_everything(self):
        result = FileTransaction(self.project).apply(self._files())
        self.assertEqual(len(result.written), 3)
        self.assertEqual((self.project / "a/one.py").read_text(), "one\n")
        self.assertEqual((self.project / "b/three.py").read_text(), "three\n")

    def test_failure_partway_through_rolls_back_all_new_files(self):
        with patch.object(FileTransaction, "_atomic_write", _make_failing_atomic_write(3)):
            with self.assertRaises(FileTransactionError):
                FileTransaction(self.project).apply(self._files())

        self.assertFalse((self.project / "a/one.py").exists())
        self.assertFalse((self.project / "a/two.py").exists())
        self.assertFalse((self.project / "b/three.py").exists())

    def test_created_parent_directories_are_removed_when_left_empty(self):
        with patch.object(FileTransaction, "_atomic_write", _make_failing_atomic_write(3)):
            with self.assertRaises(FileTransactionError):
                FileTransaction(self.project).apply(self._files())

        self.assertFalse((self.project / "a").exists())
        self.assertFalse((self.project / "b").exists())

    def test_created_directory_survives_if_it_holds_unrelated_content(self):
        (self.project / "a").mkdir()
        (self.project / "a" / "pre_existing.txt").write_text("keep me\n")

        with patch.object(FileTransaction, "_atomic_write", _make_failing_atomic_write(3)):
            with self.assertRaises(FileTransactionError):
                FileTransaction(self.project).apply(self._files())

        # "a" pre-existed (not created by this transaction) so it and its
        # unrelated file must survive untouched.
        self.assertEqual((self.project / "a" / "pre_existing.txt").read_text(), "keep me\n")
        self.assertFalse((self.project / "a" / "one.py").exists())

    def test_overwritten_file_is_restored_exactly_on_rollback(self):
        (self.project / "existing").mkdir()
        (self.project / "existing" / "config.py").write_text("ORIGINAL CONTENT\n")

        files = [
            GeneratedFile(Path("existing/config.py"), "NEW CONTENT\n", action="update"),
            GeneratedFile(Path("new/other.py"), "other\n"),
        ]
        with patch.object(FileTransaction, "_atomic_write", _make_failing_atomic_write(2)):
            with self.assertRaises(FileTransactionError):
                FileTransaction(self.project).apply(files)

        self.assertEqual((self.project / "existing/config.py").read_text(), "ORIGINAL CONTENT\n")
        self.assertFalse((self.project / "new/other.py").exists())

    def test_no_temp_files_left_behind_after_failure(self):
        with patch.object(FileTransaction, "_atomic_write", _make_failing_atomic_write(2)):
            with self.assertRaises(FileTransactionError):
                FileTransaction(self.project).apply(self._files())

        self.assertEqual(list(self.project.rglob("*archapi-tmp*")), [])

    def test_no_temp_files_left_behind_after_success(self):
        FileTransaction(self.project).apply(self._files())
        self.assertEqual(list(self.project.rglob("*archapi-tmp*")), [])

    def test_repeated_application_is_predictable(self):
        FileTransaction(self.project).apply(self._files())
        with self.assertRaises(FileExistsError):
            FileTransaction(self.project).apply(self._files())
        # First application's content must be untouched by the failed retry.
        self.assertEqual((self.project / "a/one.py").read_text(), "one\n")

    def test_absolute_path_rejected_before_any_write(self):
        files = [GeneratedFile(Path("a/one.py"), "one\n"), GeneratedFile(Path("/etc/passwd"), "x\n")]
        with self.assertRaises(PermissionError):
            FileTransaction(self.project).apply(files)
        self.assertFalse((self.project / "a/one.py").exists())

    def test_traversal_path_rejected_before_any_write(self):
        files = [GeneratedFile(Path("a/one.py"), "one\n"), GeneratedFile(Path("../outside.py"), "x\n")]
        with self.assertRaises(PermissionError):
            FileTransaction(self.project).apply(files)
        self.assertFalse((self.project / "a/one.py").exists())


class TestGenerationResultApplyDelegatesRollback(unittest.TestCase):
    def test_apply_rolls_back_on_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            plan = APIPlan(request="x", method="GET", path="/x", entities=[], layers=[], generation_allowed=True)
            files = [
                GeneratedFile(Path("a/one.py"), "one\n"),
                GeneratedFile(Path("a/two.py"), "two\n"),
            ]
            result = GenerationResult(
                project_path=project, plan=plan, files=files,
                validation_report=ValidationReport(success=True),
            )
            with patch.object(FileTransaction, "_atomic_write", _make_failing_atomic_write(2)):
                with self.assertRaises(FileTransactionError):
                    result.apply()

            self.assertFalse((project / "a").exists())


# ===========================================================================
# End-to-end: rejected/failed generation never mutates the filesystem
# ===========================================================================

class ReliabilityTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = create_fastapi_project(Path(self._tmp.name))

    def _mock_provider(self, response_files):
        provider = MagicMock()
        provider.complete.return_value = json.dumps({
            "method": "GET", "path": "/x", "entities": ["x"],
            "layers": ["route", "service", "schema", "test"],
            "files": response_files,
        })
        return provider


class TestZeroMutationOnRejection(ReliabilityTestBase):
    def test_policy_gate_rejection_zero_mutation(self):
        before = _snapshot(self.project)
        provider = self._mock_provider([{"path": "app/main.py", "content": "app = FastAPI()\n"}])
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api("Create GET API for invoice", dry_run=False)

        self.assertFalse(result.validation_report.success)
        self.assertFalse(result.policy_gate_pass)
        self.assertEqual(_snapshot(self.project), before)

    def test_framework_validation_rejection_zero_mutation(self):
        before = _snapshot(self.project)
        # Missing service/schema/test layers entirely.
        provider = self._mock_provider([{"path": "app/routers/incomplete_router.py", "content": "x = 1\n"}])
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api("Create GET API for invoice", dry_run=False)

        self.assertFalse(result.validation_report.success)
        self.assertFalse(result.framework_validation_pass)
        self.assertEqual(_snapshot(self.project), before)

    def test_path_traversal_zero_mutation(self):
        before = _snapshot(self.project)
        provider = self._mock_provider([{"path": "../outside_project.py", "content": "x = 1\n"}])
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api("Create GET API for invoice", dry_run=False)

        self.assertFalse(result.validation_report.success)
        self.assertEqual(_snapshot(self.project), before)
        self.assertFalse((self.project.parent / "outside_project.py").exists())

    def test_provider_failure_zero_mutation(self):
        before = _snapshot(self.project)
        provider = MagicMock()
        provider.complete.side_effect = LLMProviderError("simulated outage")
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        result = engine.generate_api("Create GET API for invoice", dry_run=False)

        self.assertFalse(result.validation_report.success)
        self.assertEqual(_snapshot(self.project), before)

    def test_dry_run_zero_mutation_even_when_generation_allowed(self):
        before = _snapshot(self.project)
        engine = ArchAPI(str(self.project), use_llm=False)
        result = engine.generate_api("Create GET API for invoice", dry_run=True)

        self.assertTrue(result.validation_report.success)  # would succeed if applied...
        self.assertEqual(_snapshot(self.project), before)  # ...but dry_run means nothing is written


class TestRepeatedApplicationEndToEnd(ReliabilityTestBase):
    def test_second_apply_of_same_request_fails_safely_without_corrupting_first(self):
        engine = ArchAPI(str(self.project), use_llm=False)

        first = engine.generate_api("Create GET API for invoice", dry_run=False)
        self.assertTrue(first.validation_report.success)
        first_content = (self.project / "app/routers/invoice_router.py").read_text()

        # generate_code() would recreate the same "create" files. apply()
        # raises directly (pre-existing behavior, unrelated to Phase 8D)
        # rather than returning a failed result -- the key reliability
        # guarantee is that it raises a specific, predictable exception
        # and never silently corrupts what's already on disk.
        second_engine = ArchAPI(str(self.project), use_llm=False)
        with self.assertRaises(FileExistsError):
            second_engine.generate_api("Create GET API for invoice", dry_run=False)

        self.assertEqual(
            (self.project / "app/routers/invoice_router.py").read_text(), first_content
        )


class TestMalformedOutputDoesNotCrashCli(ReliabilityTestBase):
    def test_non_json_response_does_not_crash(self):
        before = _snapshot(self.project)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake-for-test"}, clear=False):
            with patch(
                "archapi.llm.openai_provider.OpenAIProvider.complete",
                return_value="this is not json at all { broken",
            ):
                code, out, err = _run_cli(
                    ["generate", str(self.project), "Create GET API for invoice", "--llm", "--apply"]
                )
        self.assertEqual(code, cli.EXIT_REJECTED)
        self.assertNotIn("Traceback", err)
        self.assertEqual(_snapshot(self.project), before)

    def test_empty_files_list_does_not_crash(self):
        before = _snapshot(self.project)
        fake_response = json.dumps({
            "method": "GET", "path": "/x", "entities": ["x"], "layers": [], "files": [],
        })
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake-for-test"}, clear=False):
            with patch(
                "archapi.llm.openai_provider.OpenAIProvider.complete",
                return_value=fake_response,
            ):
                code, out, err = _run_cli(
                    ["generate", str(self.project), "Create GET API for invoice", "--llm", "--apply"]
                )
        self.assertIn(code, (cli.EXIT_REJECTED, cli.EXIT_OK))
        self.assertNotIn("Traceback", err)
        self.assertEqual(_snapshot(self.project), before)

    def test_missing_required_json_fields_does_not_crash(self):
        before = _snapshot(self.project)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake-for-test"}, clear=False):
            with patch(
                "archapi.llm.openai_provider.OpenAIProvider.complete",
                return_value=json.dumps({"some": "unrelated json"}),
            ):
                code, out, err = _run_cli(
                    ["generate", str(self.project), "Create GET API for invoice", "--llm", "--apply"]
                )
        self.assertEqual(code, cli.EXIT_REJECTED)
        self.assertNotIn("Traceback", err)
        self.assertEqual(_snapshot(self.project), before)


class TestNoLeftoverArtifacts(ReliabilityTestBase):
    def test_no_archapi_temp_files_after_full_failed_generate_cycle(self):
        provider = self._mock_provider([{"path": "app/main.py", "content": "app = FastAPI()\n"}])
        engine = ArchAPI(str(self.project), use_llm=True, llm_provider=provider)
        engine.generate_api("Create GET API for invoice", dry_run=False)

        leftover = [p for p in self.project.rglob("*") if "archapi-tmp" in p.name]
        self.assertEqual(leftover, [])
        # generate_api() never touches the cache directory on its own.
        self.assertFalse((self.project / ".archapi").exists())


if __name__ == "__main__":
    unittest.main()
