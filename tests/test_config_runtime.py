import importlib
import os
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import app.services.config_runtime as config_runtime


class _FakeSessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class ConfigRuntimeTests(TestCase):
    def setUp(self) -> None:
        config_runtime.invalidate_runtime_config_cache()

    def tearDown(self) -> None:
        config_runtime.invalidate_runtime_config_cache()

    def test_public_defaults_do_not_include_private_deployment_ids(self) -> None:
        self.assertIsNone(config_runtime.DEFAULTS["admin_chat_id"])
        self.assertIsNone(config_runtime.DEFAULTS["warning_chat_id"])
        self.assertIsNone(config_runtime.DEFAULTS["access_chat_id"])
        self.assertIsNone(config_runtime.DEFAULTS["member_chat_id"])
        self.assertIsNone(config_runtime.DEFAULTS["member_topic_id"])
        self.assertIsNone(config_runtime.DEFAULTS["geo_center_lat"])
        self.assertIsNone(config_runtime.DEFAULTS["geo_center_lon"])

    def test_equipment_topic_id_bootstraps_from_env(self) -> None:
        with patch.dict(os.environ, {"EQUIPMENT_TOPIC_ID": "456"}, clear=False):
            reloaded = importlib.reload(config_runtime)
            self.assertEqual(reloaded.DEFAULTS["equipment_topic_id"], 456)

        importlib.reload(config_runtime)


class ConfigRuntimeBulkTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        config_runtime.invalidate_runtime_config_cache()

    def tearDown(self) -> None:
        config_runtime.invalidate_runtime_config_cache()

    async def test_get_many_fetches_uncached_keys_in_one_query(self) -> None:
        db = object()
        fetch_values = AsyncMock(
            return_value={
                "geo_radius": "75.5",
                "weekly_limit": "4",
                "admin_chat_id": "123",
            }
        )

        with (
            patch.object(config_runtime, "RUNTIME_CONFIG_CACHE_TTL", 60),
            patch.object(
                config_runtime,
                "AsyncSessionLocal",
                new=lambda: _FakeSessionContext(db),
            ),
            patch.object(config_runtime, "get_config_values", new=fetch_values),
        ):
            values = await config_runtime.get_many(
                ["geo_radius", "weekly_limit", "admin_chat_id"]
            )
            cached_values = await config_runtime.get_many(
                ["geo_radius", "weekly_limit", "admin_chat_id"]
            )

        self.assertEqual(
            values,
            {
                "geo_radius": 75.5,
                "weekly_limit": 4,
                "admin_chat_id": 123,
            },
        )
        self.assertEqual(cached_values, values)
        fetch_values.assert_awaited_once()
        self.assertIs(fetch_values.await_args.args[0], db)
        self.assertEqual(
            fetch_values.await_args.args[1],
            ["geo_radius", "weekly_limit", "admin_chat_id"],
        )

    async def test_get_many_only_queries_uncached_keys(self) -> None:
        db = object()
        fetch_values = AsyncMock(return_value={"late_minutes": "15"})
        config_runtime._CACHE["admin_chat_id"] = (None, config_runtime.monotonic() + 60)

        with (
            patch.object(config_runtime, "RUNTIME_CONFIG_CACHE_TTL", 60),
            patch.object(
                config_runtime,
                "AsyncSessionLocal",
                new=lambda: _FakeSessionContext(db),
            ),
            patch.object(config_runtime, "get_config_values", new=fetch_values),
        ):
            values = await config_runtime.get_many(["admin_chat_id", "late_minutes"])

        self.assertEqual(values, {"admin_chat_id": None, "late_minutes": 15})
        fetch_values.assert_awaited_once()
        self.assertEqual(fetch_values.await_args.args[1], ["late_minutes"])

    async def test_get_runtime_all_has_concrete_mixed_value_type(self) -> None:
        db = object()
        fetch_values = AsyncMock(return_value={"rules_text": "House rules"})

        with (
            patch.object(config_runtime, "RUNTIME_CONFIG_CACHE_TTL", 0),
            patch.object(
                config_runtime,
                "AsyncSessionLocal",
                new=lambda: _FakeSessionContext(db),
            ),
            patch.object(config_runtime, "get_config_values", new=fetch_values),
        ):
            values: dict[str, config_runtime.RuntimeConfigValue] = (
                await config_runtime.get_runtime_all()
            )

        self.assertEqual(values["rules_text"], "House rules")
        self.assertEqual(values["geo_radius"], config_runtime.DEFAULTS["geo_radius"])
        fetch_values.assert_awaited_once()
