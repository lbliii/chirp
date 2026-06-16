"""SignalBackplane seam tests for Lucky Cat (#295).

The scaling story is visible without a working Redis deploy: a
``SignalBackplane`` protocol, the in-process default, and a stubbed Redis impl
that documents the ``workers>1`` wiring path.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.issue(295)


class TestSignalBackplane:
    def test_in_process_backplane_delegates_to_emit(self) -> None:
        from backplane import InProcessBackplane

        seen: list[tuple[str, object]] = []

        def emit(name: str, value: object) -> None:
            seen.append((name, value))

        backplane = InProcessBackplane(emit)
        backplane.publish("balance", 42)
        assert seen == [("balance", 42)]

    def test_redis_backplane_is_a_skeleton(self) -> None:
        from backplane import RedisBackplane

        bp = RedisBackplane(redis_url="redis://localhost:6379/0", emit=lambda *_: None)
        with pytest.raises(NotImplementedError, match="skeleton only"):
            bp.publish("ticker", {"symbol": "BTC-MEOW"})

    def test_get_backplane_defaults_to_in_process(self, monkeypatch) -> None:
        import backplane

        backplane.reset()
        seen: list[tuple[str, object]] = []

        def emit(name: str, value: object) -> None:
            seen.append((name, value))

        backplane.bind_emit(emit)
        monkeypatch.delenv("LUCKY_CAT_BACKPLANE", raising=False)
        bp = backplane.get_backplane()
        assert isinstance(bp, backplane.InProcessBackplane)
        bp.publish("balance", 100)
        assert seen == [("balance", 100)]

    def test_redis_env_without_url_falls_back_to_in_process(self, monkeypatch, caplog) -> None:
        import backplane

        backplane.reset()
        backplane.bind_emit(lambda *_: None)
        monkeypatch.setenv("LUCKY_CAT_BACKPLANE", "redis")
        monkeypatch.delenv("REDIS_URL", raising=False)
        bp = backplane.get_backplane()
        assert isinstance(bp, backplane.InProcessBackplane)
        assert any("REDIS_URL is unset" in record.message for record in caplog.records)

    def test_publish_before_bind_raises(self, monkeypatch) -> None:
        import backplane

        backplane.reset()
        monkeypatch.setattr(backplane, "_emit_fn", None)
        with pytest.raises(RuntimeError, match="bind_emit"):
            backplane.get_backplane()

    def test_emit_signal_calls_get_backplane(self, monkeypatch) -> None:
        import importlib.util
        from pathlib import Path

        app_path = Path(__file__).parent / "app.py"
        spec = importlib.util.spec_from_file_location("lucky_cat_app_emit_signal", app_path)
        assert spec is not None
        assert spec.loader is not None
        app_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_mod)

        seen: list[tuple[str, object]] = []

        class _FakeBackplane:
            def publish(self, name: str, value: object) -> None:
                seen.append((name, value))

        monkeypatch.setattr(app_mod, "get_backplane", lambda: _FakeBackplane())
        app_mod.emit_signal("balance", 7)
        assert seen == [("balance", 7)]
