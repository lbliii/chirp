"""Integration tests for the ``routes``, ``freeze``, and ``security-check``
CLI seams (chirp.cli._routes / _freeze / _security_check).

These commands previously had no direct test (dead-CLI-command risk). The tests
here drive the real entrypoints:

* ``run_routes`` — assert the table prints METHOD/PATH/HANDLER, and the
  defensive ``router is None`` exit-1 path.
* ``run_freeze`` — freeze a tiny app to a temp dir, assert HTML files are
  written, and assert the errors-exit-1 path when a route raises.
* ``run_security_check`` — parametrize one *failing* config per OWASP rule so
  every rule is exercised (not just one), plus the all-passing exit-0 path.

``run_freeze`` manages its own event loop via ``anyio.run``, so the freeze
tests are plain synchronous functions to avoid nesting event loops.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from chirp import App
from chirp.cli._freeze import run_freeze
from chirp.cli._routes import run_routes
from chirp.config import AppConfig


def _register_app_module(
    monkeypatch: pytest.MonkeyPatch, app: App, name: str = "_cli_seam_test_app"
) -> str:
    """Register *app* under a fake module so import strings resolve to it."""
    mod = types.ModuleType(name)
    mod.app = app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, mod)
    return f"{name}:app"


# ── routes ────────────────────────────────────────────────────────────────


class TestChirpRoutes:
    def test_prints_route_table(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """routes prints a METHOD/PATH/HANDLER table for registered routes."""
        app = App(config=AppConfig(template_dir="nonexistent"))

        @app.route("/")
        def index():
            return "ok"

        @app.route("/widgets", methods=["GET", "POST"])
        def widgets():
            return "ok"

        import_string = _register_app_module(monkeypatch, app)
        run_routes(SimpleNamespace(app=import_string))

        out = capsys.readouterr().out
        # Header row.
        assert "METHOD" in out
        assert "PATH" in out
        assert "HANDLER" in out
        # Both user routes appear with their handler names.
        assert "/widgets" in out
        assert "index" in out
        assert "widgets" in out
        # POST method shown for the multi-method route.
        assert "POST" in out

    def test_no_router_exits_one(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The defensive ``router is None`` branch exits 1 to stderr."""
        app = App(config=AppConfig(template_dir="nonexistent"))

        @app.route("/")
        def index():
            return "ok"

        import_string = _register_app_module(monkeypatch, app)

        # Force the degenerate state the guard defends against: a frozen app
        # whose router resolved to None. ``run_routes`` freezes first, so patch
        # _ensure_frozen to a no-op and null out the router alias.
        monkeypatch.setattr(App, "_ensure_frozen", lambda self: None)
        app._router = None

        with pytest.raises(SystemExit) as exc_info:
            run_routes(SimpleNamespace(app=import_string))

        assert exc_info.value.code == 1
        assert "No routes registered." in capsys.readouterr().err

    def test_invalid_import_string_exits_one(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A bad import string exits 1 with an error on stderr."""
        with pytest.raises(SystemExit) as exc_info:
            run_routes(SimpleNamespace(app="nonexistent_module_xyz:app"))
        assert exc_info.value.code == 1
        assert "Error:" in capsys.readouterr().err


# ── freeze ──────────────────────────────────────────────────────────────────


class TestChirpFreeze:
    def test_writes_html_files(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """freeze renders GET routes to static HTML and reports the count."""
        app = App(config=AppConfig(template_dir="nonexistent", debug=False))

        @app.route("/")
        def index():
            return "<html><body>home</body></html>"

        @app.route("/about")
        def about():
            return "<html><body>about</body></html>"

        import_string = _register_app_module(monkeypatch, app)
        output = tmp_path / "dist"

        run_freeze(SimpleNamespace(app=import_string, output=str(output), exclude=None))

        # Both pages rendered to disk.
        assert (output / "index.html").exists()
        assert (output / "about" / "index.html").exists()
        assert "home" in (output / "index.html").read_text()

        out = capsys.readouterr().out
        assert "Froze" in out
        assert "pages to" in out

    def test_errors_exit_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A route that errors during render makes freeze exit 1."""
        app = App(config=AppConfig(template_dir="nonexistent", debug=False))

        @app.route("/")
        def index():
            return "<html><body>home</body></html>"

        @app.route("/boom")
        def boom():
            raise RuntimeError("kaboom")

        import_string = _register_app_module(monkeypatch, app)
        output = tmp_path / "dist"

        with pytest.raises(SystemExit) as exc_info:
            run_freeze(SimpleNamespace(app=import_string, output=str(output), exclude=None))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        # The error summary surfaces the failing URL on stderr.
        assert "/boom" in captured.err
        # The healthy page was still written before the failure was reported.
        assert (output / "index.html").exists()

    def test_invalid_import_string_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A bad import string exits 1 with an error on stderr."""
        with pytest.raises(SystemExit) as exc_info:
            run_freeze(
                SimpleNamespace(
                    app="nonexistent_module_xyz:app",
                    output=str(tmp_path / "dist"),
                    exclude=None,
                )
            )
        assert exc_info.value.code == 1
        assert "Error:" in capsys.readouterr().err


# ── security-check ────────────────────────────────────────────────────────


def _passing_kwargs() -> dict[str, object]:
    """Baseline config kwargs where every OWASP rule passes."""
    return {
        "env": "production",
        "debug": False,
        "secret_key": "s3cr3t",
        "allowed_hosts": ("example.com",),
        "ssl_certfile": "cert.pem",
        "strict_transport_security": "max-age=63072000",
        "csp_nonce_enabled": True,
    }


# One failing config per rule. Each overrides exactly the field that should
# trip a single rule; ``expected`` is a distinctive substring of that rule's
# failure message. The post-init guard forbids an empty secret_key outside
# development, so the secret_key case uses env="development".
_FAILING_CONFIGS = {
    "secret_key": (
        {
            "env": "development",
            "secret_key": "",
            "ssl_certfile": None,
            "strict_transport_security": None,
        },
        "secret_key is empty",
    ),
    "allowed_hosts": (
        {"allowed_hosts": ("*",)},
        'allowed_hosts is "*" in production',
    ),
    "debug_in_production": (
        {"debug": True},
        "debug=True in production",
    ),
    "hsts": (
        {"strict_transport_security": None},
        "HSTS not enabled",
    ),
    "csp_nonce": (
        {
            "env": "development",
            "ssl_certfile": None,
            "strict_transport_security": None,
            "csp_nonce_enabled": False,
        },
        "CSP nonce not enabled",
    ),
}


class TestSecurityCheckRuleCoverage:
    @pytest.mark.parametrize(
        ("overrides", "expected"),
        list(_FAILING_CONFIGS.values()),
        ids=list(_FAILING_CONFIGS.keys()),
    )
    def test_each_rule_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        overrides: dict[str, object],
        expected: str,
    ) -> None:
        """Every OWASP rule is exercised by a config that trips exactly it."""
        from chirp.cli import _security_check

        kwargs = _passing_kwargs()
        kwargs.update(overrides)
        app = SimpleNamespace(config=AppConfig(**kwargs))
        monkeypatch.setattr(_security_check, "resolve_app", lambda _import: app)

        with pytest.raises(SystemExit) as exc_info:
            _security_check.run_security_check(SimpleNamespace(app="app:app"))

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        # The targeted rule's failure message is present...
        assert expected in out
        # ...and exactly one rule failed (a precise, non-vacuous assertion).
        fail_lines = [ln for ln in out.splitlines() if ln.strip().startswith("✗")]
        assert len(fail_lines) == 1, f"expected one failure, got {fail_lines}"

    def test_all_rules_pass_exits_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A fully hardened production config passes every rule and exits 0."""
        from chirp.cli import _security_check

        app = SimpleNamespace(config=AppConfig(**_passing_kwargs()))
        monkeypatch.setattr(_security_check, "resolve_app", lambda _import: app)

        with pytest.raises(SystemExit) as exc_info:
            _security_check.run_security_check(SimpleNamespace(app="app:app"))

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "Results: 5 passed, 0 failed" in out
