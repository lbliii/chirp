"""Tests for runtime SettingsRegistry (#370)."""

from __future__ import annotations

import json
import os

import pytest

from chirp import App, AppConfig
from chirp.contracts.rules_settings import check_settings_spec
from chirp.data.database import Database
from chirp.settings import (
    FileSettingsStore,
    SettingSpec,
    SettingsRegistry,
)
from chirp.settings.registry import _env_key_for


@pytest.mark.issue(370)
class TestSettingsRegistry:
    def test_register_and_get_default(self) -> None:
        registry = SettingsRegistry()
        registry.register(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        assert registry.get("channels") is False

    def test_precedence_env_over_persisted_over_default(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({"version": 1, "values": {"ui.enable_channels": True}}),
            encoding="utf-8",
        )
        store = FileSettingsStore(path)
        registry = SettingsRegistry(store=store)
        registry.register(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        registry.apply_persisted({"version": 1, "values": {"ui.enable_channels": True}})
        assert registry.get("channels") is True
        os.environ[_env_key_for("channels")] = "false"
        try:
            registry.apply_env()
            assert registry.get("channels") is False
        finally:
            os.environ.pop(_env_key_for("channels"), None)

    async def test_set_persists_and_survives_reload(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        store = FileSettingsStore(path)
        registry = SettingsRegistry(store=store)
        registry.register(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        await registry.set("channels", True)
        reloaded = SettingsRegistry(store=store)
        reloaded.register(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        doc = await store.load()
        reloaded.apply_persisted(doc)
        assert reloaded.get("channels") is True

    async def test_secret_not_persisted_and_redacted(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        store = FileSettingsStore(path)
        registry = SettingsRegistry(store=store)
        registry.register(
            SettingSpec(
                name="api-token",
                dotted_key="integrations.token",
                default="",
                secret=True,
            )
        )
        assert registry.export_document()["values"] == {}
        assert registry.redacted_repr()["api-token"] == "<redacted>"
        with pytest.raises(ValueError, match="secret"):
            await registry.set("api-token", "sekret")

    def test_cannot_register_after_freeze(self) -> None:
        registry = SettingsRegistry()
        registry.freeze()
        with pytest.raises(RuntimeError, match="register"):
            registry.register(
                SettingSpec(name="x", dotted_key="x.y", default=1),
            )


@pytest.mark.issue(370)
class TestAppSettings:
    def test_register_setting_before_freeze(self) -> None:
        app = App(settings="settings.json")
        app.register_setting(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        app._ensure_frozen()
        assert app.setting("channels") is False

    def test_cannot_register_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()
        with pytest.raises(RuntimeError, match="modify"):
            app.register_setting(
                SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
            )

    async def test_lifecycle_loads_file_store(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({"version": 2, "values": {"ui.enable_channels": True}}),
            encoding="utf-8",
        )
        app = App(settings=str(path))
        app.register_setting(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        await app._lifecycle._on_startup()
        assert app.setting("channels") is True

    async def test_set_setting_bumps_version_and_registers_signal(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        app = App(settings=str(path))
        app.register_setting(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        app._ensure_frozen()
        await app._lifecycle._on_startup()
        registry = app._mutable_state.signal_registry
        assert registry is not None
        assert registry.has("chirp.settings.changed")
        await app.set_setting("channels", True)
        assert app._mutable_state.settings_registry is not None
        assert app._mutable_state.settings_registry.version == 1
        assert app.setting("channels") is True

    async def test_database_store_roundtrip(self, tmp_path) -> None:
        db_path = tmp_path / "app.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()
        app = App(db=db)
        app.register_setting(
            SettingSpec(name="channels", dotted_key="ui.enable_channels", default=False)
        )
        await app.set_setting("channels", True)
        doc = await app._mutable_state.settings_registry.store.load()  # type: ignore[union-attr]
        assert doc is not None
        assert doc["values"]["ui.enable_channels"] is True
        await db.disconnect()


@pytest.mark.issue(370)
class TestSettingsContract:
    def test_shadow_boot_field_errors_in_production(self) -> None:
        spec = SettingSpec(name="debug", dotted_key="ops.debug", default=False)
        issues = check_settings_spec(
            AppConfig(env="production", secret_key="test-secret"),
            (spec,),
        )
        assert any(i.category == "settings_spec" and "shadow" in i.message for i in issues)

    def test_sensitive_non_secret_errors(self) -> None:
        spec = SettingSpec(name="token", dotted_key="auth.token", default="", secret=False)
        issues = check_settings_spec(
            AppConfig(env="production", secret_key="test-secret"),
            (spec,),
        )
        assert any("secret=True" in i.message for i in issues)
