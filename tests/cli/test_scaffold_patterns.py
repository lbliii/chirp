"""Grep-invariant tests — assert scaffold template strings match current framework idioms.

These run against the Python strings in ``chirp.cli.templates.*`` directly. No
scaffolding, no subprocess — purely textual contract. A future edit that
regresses a pattern (e.g. reintroduces ``async def handler`` or
``{% extends "_layout.html" %}`` in a page template) fails here in milliseconds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp.cli.templates import (
    PYPROJECT_TOML,
    SHELL_ITEMS_PAGE_PY,
    SHELL_LAYOUT_HTML,
    SHELL_PAGE_PY,
    SSE_INDEX_HTML,
    V2_APP_CHIRPUI_PY,
    V2_APP_PY,
    V2_DASHBOARD_CHIRPUI_HTML,
    V2_DASHBOARD_HTML,
    V2_DASHBOARD_PAGE_PY,
    V2_INDEX_CHIRPUI_HTML,
    V2_INDEX_HTML,
    V2_INDEX_PAGE_PY,
    V2_LOGIN_CHIRPUI_HTML,
    V2_LOGIN_HTML,
    V2_LOGIN_PAGE_PY,
)

V2_PAGE_TEMPLATES = {
    "V2_INDEX_HTML": V2_INDEX_HTML,
    "V2_INDEX_CHIRPUI_HTML": V2_INDEX_CHIRPUI_HTML,
    "V2_LOGIN_HTML": V2_LOGIN_HTML,
    "V2_LOGIN_CHIRPUI_HTML": V2_LOGIN_CHIRPUI_HTML,
    "V2_DASHBOARD_HTML": V2_DASHBOARD_HTML,
    "V2_DASHBOARD_CHIRPUI_HTML": V2_DASHBOARD_CHIRPUI_HTML,
}

V2_PAGE_MODULES = {
    "V2_INDEX_PAGE_PY": V2_INDEX_PAGE_PY,
    "V2_LOGIN_PAGE_PY": V2_LOGIN_PAGE_PY,
    "V2_DASHBOARD_PAGE_PY": V2_DASHBOARD_PAGE_PY,
}

SHELL_PAGE_MODULES = {
    "SHELL_PAGE_PY": SHELL_PAGE_PY,
    "SHELL_ITEMS_PAGE_PY": SHELL_ITEMS_PAGE_PY,
}

ALL_PAGE_MODULES = {**V2_PAGE_MODULES, **SHELL_PAGE_MODULES}


class TestHandlerNames:
    """Sprint 2 invariant: no scaffold uses ``async def handler`` or ``def handler(``."""

    @pytest.mark.parametrize(("name", "src"), ALL_PAGE_MODULES.items())
    def test_no_legacy_handler_name(self, name: str, src: str) -> None:
        assert "async def handler" not in src, f"{name} uses legacy 'async def handler'"
        assert "def handler(" not in src, f"{name} uses legacy 'def handler('"

    @pytest.mark.parametrize(("name", "src"), V2_PAGE_MODULES.items())
    def test_v2_handlers_use_method_named(self, name: str, src: str) -> None:
        # At least one of get/post must be defined; the router dispatches by name.
        assert "def get(" in src or "def post(" in src, (
            f"{name} must define def get(...) and/or def post(...)"
        )


class TestV2PageTemplates:
    """Sprint 4 invariant: composition blocks (no ``extends _layout.html``)."""

    @pytest.mark.parametrize(("name", "src"), V2_PAGE_TEMPLATES.items())
    def test_declares_page_root_block(self, name: str, src: str) -> None:
        assert "{% block page_root %}" in src, f"{name} missing page_root block"

    @pytest.mark.parametrize(("name", "src"), V2_PAGE_TEMPLATES.items())
    def test_declares_page_content_block(self, name: str, src: str) -> None:
        assert "{% block page_content %}" in src, f"{name} missing page_content block"

    @pytest.mark.parametrize(("name", "src"), V2_PAGE_TEMPLATES.items())
    def test_does_not_extend_layout(self, name: str, src: str) -> None:
        assert '{% extends "_layout.html" %}' not in src, (
            f"{name} must not {{% extends '_layout.html' %}} — pages compose via "
            "render_with_layouts into the layout's {% block content %} slot."
        )


class TestV2Handlers:
    """Sprint 4 invariant: handlers use ``Page(..., page_block_name='page_root', ...)``."""

    @pytest.mark.parametrize(("name", "src"), V2_PAGE_MODULES.items())
    def test_returns_page_with_block_name(self, name: str, src: str) -> None:
        assert 'page_block_name="page_root"' in src, (
            f"{name} must pass page_block_name='page_root' to Page(...)"
        )


class TestV2LoginFlow:
    """Sprint 3 invariant: bad creds return ``Page(..., error=...)``, not ``Redirect``."""

    def test_login_does_not_redirect_with_error_query(self) -> None:
        assert "error=1" not in V2_LOGIN_PAGE_PY, (
            "Login POST must return Page(..., error=...), not Redirect('/login?error=1')"
        )

    def test_login_get_does_not_read_error_query(self) -> None:
        assert 'request.query.get("error"' not in V2_LOGIN_PAGE_PY, (
            "Login GET must not pre-fill error from ?error= query param"
        )

    def test_login_post_returns_page_on_bad_creds(self) -> None:
        assert "Invalid username or password" in V2_LOGIN_PAGE_PY


class TestAppImports:
    """Sprint 1 invariant: no dead imports in generated app.py."""

    def test_v2_plain_has_no_dead_imports(self) -> None:
        # Plain v2 does not define /time (SSE) — drop EventStream + Fragment.
        assert "EventStream" not in V2_APP_PY, (
            "V2_APP_PY imports EventStream but defines no SSE routes"
        )
        assert "Fragment" not in V2_APP_PY, "V2_APP_PY imports Fragment but emits no fragments"

    def test_v2_chirpui_has_no_bare_chirp_ui_import(self) -> None:
        # use_chirp_ui(app) handles registration — a bare ``import chirp_ui`` is dead.
        for line in V2_APP_CHIRPUI_PY.splitlines():
            assert line.strip() != "import chirp_ui", (
                "V2_APP_CHIRPUI_PY must not contain bare 'import chirp_ui'"
            )


class TestVersionFloors:
    """Sprint 1 invariant: version floors match the root pyproject."""

    def _root_pyproject_text(self) -> str:
        # tests/cli/test_scaffold_patterns.py → repo root is 3 parents up.
        root = Path(__file__).resolve().parents[2] / "pyproject.toml"
        return root.read_text(encoding="utf-8")

    def test_bengal_chirp_floor_matches_root_version(self) -> None:
        root = self._root_pyproject_text()
        # Root declares its own version (not a bengal-chirp dep), but the scaffold
        # pins bengal-chirp to that version. Extract root ``version = "x.y.z"``.
        import re

        match = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.\d+"', root, re.MULTILINE)
        assert match, "Could not find version in root pyproject.toml"
        major, minor = match.group(1), match.group(2)
        expected = f'"bengal-chirp>={major}.{minor}.'
        assert expected in PYPROJECT_TOML, (
            f"Scaffold PYPROJECT_TOML bengal-chirp floor must start with "
            f"{expected} (current root version is {major}.{minor}.x)"
        )

    def test_chirp_ui_floor_matches_root_ui_extra(self) -> None:
        root = self._root_pyproject_text()
        import re

        match = re.search(r'ui\s*=\s*\[\s*"chirp-ui>=([\d.]+)"', root)
        assert match, (
            "Could not find chirp-ui pin in root pyproject's [project.optional-dependencies].ui"
        )
        expected = f'"chirp-ui>={match.group(1)}"'
        assert expected in PYPROJECT_TOML, (
            f"Scaffold PYPROJECT_TOML must pin {expected} to match root ui extra"
        )


class TestOOBShowcase:
    """Sprint 5 invariant: chirpui dashboard teaches OOB two-target swap."""

    def test_dashboard_uses_oob_import(self) -> None:
        assert "OOB" in V2_APP_CHIRPUI_PY
        assert "/dashboard/refresh" in V2_APP_CHIRPUI_PY

    def test_dashboard_template_defines_refresh_blocks(self) -> None:
        assert "{% block refresh_counter %}" in V2_DASHBOARD_CHIRPUI_HTML
        assert "{% block refresh_stamp %}" in V2_DASHBOARD_CHIRPUI_HTML

    def test_dashboard_uses_safe_region_for_mutation_target(self) -> None:
        # Mutation target (hx-target=#refresh-counter) must use safe_region
        # so htmx doesn't inherit shell-level hx-select/hx-target/hx-swap.
        assert 'safe_region("refresh-counter")' in V2_DASHBOARD_CHIRPUI_HTML


class TestLiveUpdateScaffolds:
    """Live-update scaffolds keep listeners and transitions scoped safely."""

    def test_sse_template_uses_persistent_sse_scope_block(self) -> None:
        assert "{% block sse_scope %}" in SSE_INDEX_HTML
        assert '{{ sse_scope("/stream", swap="stream_block") }}' in SSE_INDEX_HTML
        content = SSE_INDEX_HTML.split("{% block content %}", 1)[1].split("{% end %}", 1)[0]
        assert "sse-connect" not in content

    def test_plain_shell_does_not_transition_broad_main(self) -> None:
        main_tag = next(line for line in SHELL_LAYOUT_HTML.splitlines() if 'id="main"' in line)
        assert "transition:true" not in main_tag
