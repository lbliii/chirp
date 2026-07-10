"""Signal publication seam tests for Lucky Cat (#295, #699)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.issue(295)


class TestSignalBackplane:
    def test_in_process_backplane_delegates_to_emit(self) -> None:
        from backplane import InProcessBackplane

        seen: list[tuple[str, object]] = []

        def emit(name: str, value: object, *, audience_key: str = "") -> None:
            seen.append((name, value))

        backplane = InProcessBackplane(emit)
        backplane.publish("balance", 42)
        assert seen == [("balance", 42)]

    @pytest.mark.issue(699)
    def test_redis_label_delegates_to_framework_emit(self) -> None:
        from backplane import RedisBackplane

        seen: list[tuple[str, object]] = []

        def emit(name: str, value: object, *, audience_key: str = "") -> None:
            seen.append((name, value))

        bp = RedisBackplane(emit=emit)
        bp.publish("ticker", {"symbol": "BTC-MEOW"})
        assert seen == [("ticker", {"symbol": "BTC-MEOW"})]

    def test_get_backplane_defaults_to_in_process(self, monkeypatch) -> None:
        import backplane

        backplane.reset()
        seen: list[tuple[str, object]] = []

        def emit(name: str, value: object, *, audience_key: str = "") -> None:
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
        monkeypatch.delenv("CHIRP_REDIS_URL", raising=False)
        bp = backplane.get_backplane()
        assert isinstance(bp, backplane.InProcessBackplane)
        assert any("CHIRP_REDIS_URL is unset" in record.message for record in caplog.records)

    def test_publish_before_bind_raises(self, monkeypatch) -> None:
        import backplane

        backplane.reset()
        monkeypatch.setattr(backplane, "_emit_fn", None)
        with pytest.raises(RuntimeError, match="bind_emit"):
            backplane.get_backplane()

    def test_emit_signal_calls_get_backplane(self, monkeypatch) -> None:
        import sys
        from pathlib import Path

        root = Path(__file__).parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import wiring.app_factory as app_factory
        from wiring.app_factory import emit_signal

        seen: list[tuple[str, object]] = []

        class _FakeBackplane:
            def publish(self, name: str, value: object, *, audience_key: str = "") -> None:
                seen.append((name, value))

        monkeypatch.setattr(app_factory, "get_backplane", lambda: _FakeBackplane())
        emit_signal("balance", 7, audience_key="visitor-1")
        assert seen == [("balance", 7)]
