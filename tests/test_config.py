import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archapi.config import ArchAPIConfig, ArchAPIConfigError, load_config


class TestArchAPIConfigDefaults(unittest.TestCase):
    def test_safe_defaults(self):
        config = ArchAPIConfig()
        self.assertFalse(config.use_llm)
        self.assertEqual(config.llm_provider, "openai")
        self.assertEqual(config.llm_model, "gpt-4o-mini")
        self.assertFalse(config.strict_validation)
        self.assertGreater(config.context_max_chars, 0)

    def test_to_dict_has_no_credential_field(self):
        data = ArchAPIConfig().to_dict()
        for key in data:
            self.assertNotIn("key", key.lower())
            self.assertNotIn("secret", key.lower())
            self.assertNotIn("token", key.lower())
            self.assertNotIn("credential", key.lower())

    def test_to_context_budget_maps_fields_correctly(self):
        config = ArchAPIConfig(
            routes_limit=5, controllers_limit=4, services_limit=3,
            schemas_limit=2, models_limit=1, tests_limit=6,
            auth_patterns_limit=2, validation_patterns_limit=2,
            context_max_chars=9999,
        )
        budget = config.to_context_budget()
        self.assertEqual(budget.routes, 5)
        self.assertEqual(budget.controllers, 4)
        self.assertEqual(budget.services, 3)
        self.assertEqual(budget.schemas, 2)
        self.assertEqual(budget.models, 1)
        self.assertEqual(budget.tests, 6)
        self.assertEqual(budget.auth_patterns, 2)
        self.assertEqual(budget.validation_patterns, 2)
        self.assertEqual(budget.global_char_budget, 9999)


class TestArchAPIConfigValidation(unittest.TestCase):
    def test_unknown_provider_fails_safely(self):
        with self.assertRaises(ArchAPIConfigError):
            ArchAPIConfig(llm_provider="not-a-real-provider")

    def test_negative_limit_fails_safely(self):
        with self.assertRaises(ArchAPIConfigError):
            ArchAPIConfig(routes_limit=-1)

    def test_non_int_limit_fails_safely(self):
        with self.assertRaises(ArchAPIConfigError):
            ArchAPIConfig(routes_limit="two")  # type: ignore[arg-type]

    def test_bool_rejected_as_int_limit(self):
        # bool is technically an int subclass in Python -- must not sneak
        # through the int-limit validation.
        with self.assertRaises(ArchAPIConfigError):
            ArchAPIConfig(routes_limit=True)  # type: ignore[arg-type]

    def test_empty_model_name_fails_safely(self):
        with self.assertRaises(ArchAPIConfigError):
            ArchAPIConfig(llm_model="")


class TestEnvironmentVariablePrecedence(unittest.TestCase):
    def test_env_vars_are_applied(self):
        env = {
            "ARCHAPI_USE_LLM": "true",
            "ARCHAPI_LLM_MODEL": "gpt-5-mini",
            "ARCHAPI_ROUTES_LIMIT": "7",
            "ARCHAPI_STRICT_VALIDATION": "true",
        }
        with patch.dict("os.environ", env, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                config = load_config(tmp)
        self.assertTrue(config.use_llm)
        self.assertEqual(config.llm_model, "gpt-5-mini")
        self.assertEqual(config.routes_limit, 7)
        self.assertTrue(config.strict_validation)

    def test_invalid_bool_env_var_fails_safely(self):
        with patch.dict("os.environ", {"ARCHAPI_USE_LLM": "maybe"}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ArchAPIConfigError):
                    load_config(tmp)

    def test_invalid_int_env_var_fails_safely(self):
        with patch.dict("os.environ", {"ARCHAPI_ROUTES_LIMIT": "not-a-number"}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ArchAPIConfigError):
                    load_config(tmp)


class TestProjectConfigFile(unittest.TestCase):
    def test_toml_file_is_loaded_and_flattened(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "archapi.toml").write_text(
                "[archapi]\n"
                "use_llm = true\n"
                "strict_validation = true\n\n"
                "[archapi.llm]\n"
                'provider = "openai"\n'
                'model = "gpt-5-mini"\n\n'
                "[archapi.retrieval]\n"
                "max_chars = 5000\n"
                "routes = 1\n"
                "services = 3\n"
            )
            config = load_config(tmp)

        self.assertTrue(config.use_llm)
        self.assertTrue(config.strict_validation)
        self.assertEqual(config.llm_model, "gpt-5-mini")
        self.assertEqual(config.context_max_chars, 5000)
        self.assertEqual(config.routes_limit, 1)
        self.assertEqual(config.services_limit, 3)

    def test_absent_config_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(tmp)
        self.assertEqual(config, ArchAPIConfig())

    def test_malformed_toml_fails_safely_not_a_raw_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "archapi.toml").write_text("[archapi\nuse_llm = true\n")  # unclosed bracket
            with self.assertRaises(ArchAPIConfigError):
                load_config(tmp)

    def test_wrong_typed_toml_value_fails_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "archapi.toml").write_text(
                "[archapi.retrieval]\nroutes = \"two\"\n"
            )
            with self.assertRaises(ArchAPIConfigError):
                load_config(tmp)

    def test_api_key_in_toml_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "archapi.toml").write_text(
                "[archapi.llm]\n"
                'provider = "openai"\n'
                'api_key = "sk-should-never-be-here"\n'
            )
            with self.assertRaises(ArchAPIConfigError) as ctx:
                load_config(tmp)
        self.assertNotIn("sk-should-never-be-here", str(ctx.exception))

    def test_secret_like_key_variants_are_all_rejected(self):
        for bad_key in ("secret", "token", "password", "credential", "client_secret"):
            with self.subTest(bad_key=bad_key):
                with tempfile.TemporaryDirectory() as tmp:
                    (Path(tmp) / "archapi.toml").write_text(
                        f'[archapi]\n{bad_key} = "whatever"\n'
                    )
                    with self.assertRaises(ArchAPIConfigError):
                        load_config(tmp)


class TestOverridesPrecedence(unittest.TestCase):
    def test_overrides_beat_toml_beat_env_beat_default(self):
        env = {"ARCHAPI_ROUTES_LIMIT": "3", "ARCHAPI_LLM_MODEL": "env-model"}
        with patch.dict("os.environ", env, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                # No file: env should win over default.
                config = load_config(tmp)
                self.assertEqual(config.routes_limit, 3)
                self.assertEqual(config.llm_model, "env-model")

                # File present: file should win over env for the fields it sets.
                (Path(tmp) / "archapi.toml").write_text(
                    "[archapi.retrieval]\nroutes = 9\n"
                )
                config = load_config(tmp)
                self.assertEqual(config.routes_limit, 9)          # file beats env
                self.assertEqual(config.llm_model, "env-model")   # env still applies (file silent on it)

                # Explicit override beats everything.
                config = load_config(tmp, overrides={"routes_limit": 1, "llm_model": "override-model"})
                self.assertEqual(config.routes_limit, 1)
                self.assertEqual(config.llm_model, "override-model")

    def test_secret_like_key_in_overrides_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ArchAPIConfigError):
                load_config(tmp, overrides={"api_key": "sk-nope"})

    def test_unknown_override_key_fails_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ArchAPIConfigError):
                load_config(tmp, overrides={"not_a_real_field": 1})


if __name__ == "__main__":
    unittest.main()
