"""Tests for chirp.cli._resolve — App import resolution."""

import types

import pytest

from chirp.cli._resolve import resolve_app


@pytest.fixture
def _fake_app_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register a fake module with a chirp App on sys.modules."""
    from chirp.app import App

    mod = types.ModuleType("_fake_chirp_app")
    mod.app = App()  # type: ignore[attr-defined]
    mod.custom = App()  # type: ignore[attr-defined]
    mod.not_an_app = "just a string"  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "_fake_chirp_app", mod)


@pytest.mark.usefixtures("_fake_app_module")
class TestResolveApp:
    def test_explicit_attribute(self) -> None:
        app = resolve_app("_fake_chirp_app:app")
        from chirp.app import App

        assert isinstance(app, App)

    def test_custom_attribute(self) -> None:
        app = resolve_app("_fake_chirp_app:custom")
        from chirp.app import App

        assert isinstance(app, App)

    def test_default_attribute(self) -> None:
        """Omitting :attr defaults to 'app'."""
        app = resolve_app("_fake_chirp_app")
        from chirp.app import App

        assert isinstance(app, App)

    def test_missing_module(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            resolve_app("nonexistent_module_xyz:app")

    def test_missing_attribute(self) -> None:
        with pytest.raises(AttributeError):
            resolve_app("_fake_chirp_app:does_not_exist")

    def test_wrong_type(self) -> None:
        with pytest.raises(TypeError, match=r"not a chirp\.App instance"):
            resolve_app("_fake_chirp_app:not_an_app")
