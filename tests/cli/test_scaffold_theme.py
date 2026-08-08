"""Acceptance tests for app-owned semantic tokens + theme selection (#858)."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp.cli.templates import (
    BASE_CSS,
    COMPONENTS_CSS,
    PAGES_CSS,
    PATTERNS_CSS,
    THEME_JS,
    TOKENS_CSS,
    V2_APP_PY,
    V2_LAYOUT_HTML,
)
from tests.cli.conftest import run_and_parse, scaffold


@pytest.mark.issue(858)
def test_default_scaffold_ships_layered_theme_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode="v2")

    for name in ("tokens.css", "base.css", "components.css", "patterns.css", "pages.css"):
        path = project / "static" / "css" / name
        assert path.is_file(), name
        assert "{{" not in path.read_text(encoding="utf-8")

    assert (project / "static" / "js" / "theme.js").is_file()
    assert (project / "static" / "js" / "interactions.js").is_file()
    assert (project / "theme.py").is_file()
    assert (project / "pages" / "_context.py").is_file()
    assert not (project / "static" / "style.css").exists()

    layout = (project / "pages" / "_layout.html").read_text(encoding="utf-8")
    assert 'data-theme="{{ theme }}"' in layout
    assert "/static/css/tokens.css" in layout
    assert "/static/js/theme.js" in layout
    assert 'action="/theme"' in layout
    assert 'hx-boost="false"' in layout
    assert "alpine" not in layout.lower()
    assert "<script>" not in layout  # no inline script — CSP-safe first paint


@pytest.mark.issue(858)
def test_theme_template_strings_cover_contract_surface() -> None:
    assert "--color-bg:" in TOKENS_CSS
    assert '[data-theme="dark"]' in TOKENS_CSS
    assert '[data-theme="system"]' in TOKENS_CSS
    assert "prefers-color-scheme" in TOKENS_CSS
    assert "prefers-reduced-motion" in TOKENS_CSS
    assert "forced-colors" in BASE_CSS
    assert ":focus-visible" in BASE_CSS
    assert ".panel" in COMPONENTS_CSS
    assert ".theme-control" in COMPONENTS_CSS
    assert ".app-nav" in PAGES_CSS
    assert "account-summary" in PATTERNS_CSS or ".account-summary" in PATTERNS_CSS
    assert "data-theme-control" in THEME_JS
    assert "x-data" not in THEME_JS
    assert "Alpine." not in THEME_JS
    assert 'data-theme="{{ theme }}"' in V2_LAYOUT_HTML
    assert '@app.route("/theme"' in V2_APP_PY


_THEME_RUNTIME = r"""
import asyncio, json, re, sys

sys.path.insert(0, ".")
from app import app
from chirp.testing import TestClient


def csrf(html):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None


def cookie(response, name="chirp_theme"):
    for header, value in response.headers:
        if header == "set-cookie" and value.startswith(f"{name}="):
            return value.split(";", 1)[0].partition("=")[2]
    return None


def session(response):
    for header, value in response.headers:
        if header == "set-cookie" and value.startswith("chirp_session="):
            return value.split(";", 1)[0].partition("=")[2]
    return None


async def exercise():
    out = {}
    async with TestClient(app) as client:
        home = await client.get("/")
        out["default_theme"] = 'data-theme="system"' in home.text
        out["has_tokens_link"] = "/static/css/tokens.css" in home.text
        out["csp"] = None
        for name, value in home.headers:
            if name.lower() == "content-security-policy":
                out["csp"] = value
                break
        out["csp_self"] = bool(out["csp"] and "'self'" in out["csp"])
        out["no_unsafe_inline_script"] = bool(
            out["csp"] and "script-src" in out["csp"] and "unsafe-inline" not in out["csp"].split("script-src", 1)[1].split(";", 1)[0]
        )

        token = csrf(home.text)
        sess = session(home)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"chirp_session={sess}",
        }
        set_dark = await client.post(
            "/theme",
            body=f"theme=dark&next=/&_csrf_token={token}".encode(),
            headers=headers,
        )
        theme_cookie = cookie(set_dark)
        out["set_status"] = set_dark.status
        out["set_cookie"] = theme_cookie
        loc = ""
        for name, value in set_dark.headers:
            if name == "location":
                loc = value
        out["set_location"] = loc

        themed = await client.get(
            "/",
            headers={"Cookie": f"chirp_session={sess}; chirp_theme={theme_cookie}"},
        )
        out["persisted_theme"] = 'data-theme="dark"' in themed.text
        out["dark_checked"] = 'value="dark" checked' in themed.text or 'value="dark" checked>' in themed.text

        # HTMX fragment swap must not recompute/replace the root theme attribute
        # (fragments omit <html>); preference still lives on full navigations.
        fragment = await client.get(
            "/",
            headers={
                "Cookie": f"chirp_session={sess}; chirp_theme={theme_cookie}",
                "HX-Request": "true",
            },
        )
        out["fragment_has_html"] = "<html" in fragment.text.lower()
        out["fragment_ok"] = fragment.status == 200 and "Welcome" in fragment.text

        # Invalid theme values fall back to system without writing garbage.
        bad = await client.post(
            "/theme",
            body=f"theme=neon&next=/&_csrf_token={token}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={sess}; chirp_theme={theme_cookie}",
            },
        )
        out["invalid_cookie"] = cookie(bad)

        tokens = await client.get("/static/css/tokens.css")
        theme_js = await client.get("/static/js/theme.js")
        out["tokens_status"] = tokens.status
        out["theme_js_status"] = theme_js.status
        out["tokens_has_system"] = "[data-theme=\"system\"]" in tokens.text

    print(json.dumps(out))


asyncio.run(exercise())
"""


@pytest.mark.issue(858)
def test_generated_theme_preference_round_trip_and_csp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode="v2")
    result = run_and_parse(project, _THEME_RUNTIME)
    assert result.returncode == 0, result.stderr
    payload = result.payload
    assert payload["default_theme"] is True
    assert payload["has_tokens_link"] is True
    assert payload["csp_self"] is True
    assert payload["no_unsafe_inline_script"] is True
    assert payload["set_status"] == 303
    assert payload["set_cookie"] == "dark"
    assert payload["set_location"] == "/"
    assert payload["persisted_theme"] is True
    assert payload["fragment_has_html"] is False
    assert payload["fragment_ok"] is True
    assert payload["invalid_cookie"] == "system"
    assert payload["tokens_status"] == 200
    assert payload["theme_js_status"] == 200
    assert payload["tokens_has_system"] is True


@pytest.mark.issue(858)
def test_shell_scaffold_also_ships_theme_layers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode="shell")
    assert (project / "static" / "css" / "tokens.css").is_file()
    assert (project / "theme.py").is_file()
    layout = (project / "pages" / "_layout.html").read_text(encoding="utf-8")
    assert 'data-theme="{{ theme }}"' in layout
    assert "/theme" in (project / "app.py").read_text(encoding="utf-8")
