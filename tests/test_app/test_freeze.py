"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

import pytest

from chirp import App
from chirp.config import AppConfig


class TestAppFreeze:
    def test_freeze_compiles_router(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "hello"

        app._ensure_frozen()
        assert app._frozen is True
        assert app._router is not None

    def test_freeze_marks_contracts_ready(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "ok"

        app._ensure_frozen()
        assert app._runtime_state.contracts_ready is True

    def test_debug_checks_run_after_runtime_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from chirp.contracts.types import CheckResult

        app = App(config=AppConfig(debug=True))

        @app.route("/")
        def index():
            return "ok"

        seen = {"called": False}

        def fake_check(app_obj: App) -> CheckResult:
            seen["called"] = True
            assert app_obj._router is not None
            assert app_obj._runtime_state.contracts_ready is True
            return CheckResult()

        monkeypatch.setattr("chirp.contracts.check_hypermedia_surface", fake_check)
        app._ensure_frozen()
        assert seen["called"] is True

    def test_debug_fail_fast_still_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from chirp.contracts.types import CheckResult, ContractIssue, Severity

        app = App(config=AppConfig(debug=True))

        @app.route("/")
        def index():
            return "ok"

        def fake_check(_: App) -> CheckResult:
            return CheckResult(
                issues=[
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="setup",
                        message="boom",
                    )
                ]
            )

        monkeypatch.setattr("chirp.contracts.check_hypermedia_surface", fake_check)
        with pytest.raises(SystemExit):
            app._ensure_frozen()

    def test_cannot_add_routes_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        with pytest.raises(RuntimeError, match="Cannot modify"):

            @app.route("/")
            def index():
                return "hello"

    def test_cannot_add_middleware_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        async def mw(request, next):
            return await next(request)

        with pytest.raises(RuntimeError, match="Cannot modify"):
            app.add_middleware(mw)

    def test_double_freeze_is_safe(self) -> None:
        app = App()
        app._ensure_frozen()
        app._ensure_frozen()  # Should not raise
        assert app._frozen is True
