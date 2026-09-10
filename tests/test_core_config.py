import importlib
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

import dotenv

import app.core.config as config


class CoreConfigTests(TestCase):
    def reload_config(self) -> object:
        with patch.object(dotenv, "load_dotenv", return_value=False):
            return importlib.reload(config)

    def tearDown(self) -> None:
        self.reload_config()

    def test_normalizes_common_postgres_urls_for_async_sqlalchemy(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgres://user:pass@postgres:5432/musicroom"},
            clear=True,
        ):
            reloaded = self.reload_config()

        self.assertEqual(
            reloaded.DATABASE_URL,
            "postgresql+asyncpg://user:pass@postgres:5432/musicroom",
        )

    def test_reads_secret_file_fallback(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as secret:
            secret.write("token-from-file\n")
            secret.flush()

            with patch.dict(os.environ, {"BOT_TOKEN_FILE": secret.name}, clear=True):
                reloaded = self.reload_config()

        self.assertEqual(reloaded.BOT_TOKEN, "token-from-file")

    def test_env_value_wins_over_secret_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as secret:
            secret.write("token-from-file\n")
            secret.flush()

            with patch.dict(
                os.environ,
                {"BOT_TOKEN": "token-from-env", "BOT_TOKEN_FILE": secret.name},
                clear=True,
            ):
                reloaded = self.reload_config()

        self.assertEqual(reloaded.BOT_TOKEN, "token-from-env")

    def test_log_level_defaults_to_info(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            reloaded = self.reload_config()

        self.assertEqual(reloaded.LOG_LEVEL, "INFO")

    def test_log_level_is_normalized(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": " debug "}, clear=True):
            reloaded = self.reload_config()

        self.assertEqual(reloaded.LOG_LEVEL, "DEBUG")

    def test_unknown_log_level_falls_back_to_info(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "verbose"}, clear=True):
            reloaded = self.reload_config()

        self.assertEqual(reloaded.LOG_LEVEL, "INFO")

    def test_access_form_url_defaults_to_google_form(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            reloaded = self.reload_config()

        self.assertEqual(reloaded.ACCESS_FORM_URL, "https://forms.gle/YEiqGNfKt7fAbqFP9")

    def test_access_form_url_reads_env(self) -> None:
        with patch.dict(
            os.environ,
            {"ACCESS_FORM_URL": "https://forms.example.test/apply"},
            clear=True,
        ):
            reloaded = self.reload_config()

        self.assertEqual(reloaded.ACCESS_FORM_URL, "https://forms.example.test/apply")
