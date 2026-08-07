"""Contract checks for chirp-ui Alpine runtime wiring (#191)."""

from __future__ import annotations

from pathlib import Path

import pytest

chirp_ui = pytest.importorskip("chirp_ui")

from chirp import App, AppConfig, Template  # noqa: E402
from chirp.contracts import check_hypermedia_surface  # noqa: E402
from chirp.contracts.types import Severity  # noqa: E402
from chirp.ext.chirp_ui import use_chirp_ui  # noqa: E402

_PAGE = (
    "<!DOCTYPE html><html><head></head><body>"
    '{% from "chirpui/theme_toggle.html" import theme_toggle %}'
    "{{ theme_toggle() }}"
    "</body></html>"
)
_STATIC_PAGE = (
    "<!DOCTYPE html><html><head></head><body>"
    '{% from "chirpui/card.html" import card %}'
    "{{ card(title='Static') }}"
    "</body></html>"
)


class TestChirpUIAlpineRuntimeContract:
    def test_wired_app_passes_probe(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(_PAGE)
        app = App(AppConfig(template_dir=str(tmp_path), debug=True))
        use_chirp_ui(app)

        @app.route("/")
        def index():
            return Template("page.html")

        result = check_hypermedia_surface(app)
        runtime_issues = [i for i in result.issues if i.category == "chirpui_alpine_runtime"]
        assert runtime_issues == []

    def test_missing_runtime_script_is_error_in_debug(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(_PAGE)
        app = App(
            AppConfig(
                template_dir=str(tmp_path),
                debug=True,
                alpine=False,
                skip_contract_checks=True,
            )
        )
        # Explicit-loading contract (#860): register the chirp-ui template loader
        # and filters WITHOUT use_chirp_ui(app) (which would force alpine=True and
        # inject the runtime). This is the documented "equivalent explicit
        # App.add_loader + filter integration" path — the app renders chirp-ui
        # interactive macros but never wires chirpui-alpine.js, which is exactly
        # the mismatch this rule must catch.
        from kida import PackageLoader

        app.add_loader(PackageLoader("chirp_ui", "templates"))
        chirp_ui.register_filters(app)
        app.set_contract_check_data("chirpui_components", frozenset(["card.html"]))

        @app.route("/")
        def index():
            return Template("page.html")

        result = check_hypermedia_surface(app)
        runtime_issues = [i for i in result.issues if i.category == "chirpui_alpine_runtime"]
        assert len(runtime_issues) == 1
        assert runtime_issues[0].severity == Severity.ERROR
        assert "chirpui-alpine.js" in (runtime_issues[0].details or "")

    def test_no_interactive_pages_skips_probe(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(_STATIC_PAGE)
        app = App(AppConfig(template_dir=str(tmp_path), debug=True))
        use_chirp_ui(app)

        @app.route("/")
        def index():
            return Template("page.html")

        result = check_hypermedia_surface(app)
        runtime_issues = [i for i in result.issues if i.category == "chirpui_alpine_runtime"]
        assert runtime_issues == []
