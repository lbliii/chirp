"""Contracts for the app-owned modular default scaffold (#863)."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp.cli import main
from tests.cli.conftest import run_and_parse, scaffold


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.mark.issue(863)
@pytest.mark.parametrize("mode_args", [[], ["--shell"]], ids=["default", "shell"])
def test_default_scaffold_is_independent_of_chirpui_presence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode_args: list[str],
) -> None:
    """Package presence cannot change default generated files or bytes."""
    from chirp.cli import _new

    without_ui = tmp_path / "without-ui"
    with_ui = tmp_path / "with-ui"
    without_ui.mkdir()
    with_ui.mkdir()

    monkeypatch.setattr(_new, "_has_chirpui", lambda: False)
    monkeypatch.chdir(without_ui)
    main(["new", "project", *mode_args])

    monkeypatch.setattr(_new, "_has_chirpui", lambda: True)
    monkeypatch.chdir(with_ui)
    main(["new", "project", *mode_args])

    assert _snapshot(without_ui / "project") == _snapshot(with_ui / "project")


@pytest.mark.issue(863)
def test_default_scaffold_teaches_explicit_template_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode="v2")

    app = (project / "app.py").read_text()
    page = (project / "pages" / "dashboard" / "page.html").read_text()
    component = (project / "templates" / "components" / "chrome" / "panel.html").read_text()
    pattern = (project / "templates" / "patterns" / "account_summary.html").read_text()

    assert 'component_dirs=(ROOT / "templates",)' in app
    assert "{% block page_root %}" in page
    assert "{% block page_content %}" in page
    assert 'from "patterns/account_summary.html" import account_summary' in page
    assert "{% def panel(title: str, heading_id: str) %}" in component
    assert "{% slot %}" in component
    assert 'aria-labelledby="{{ heading_id }}"' in component
    assert 'from "components/chrome/panel.html" import panel' in pattern
    assert "{% block " not in pattern
    assert (project / "templates" / "_partials" / ".gitkeep").is_file()
    assert "{{" not in (project / "static" / "css" / "tokens.css").read_text()


_REQUEST_POSTURES = r"""
import asyncio, json, re, sys

sys.path.insert(0, ".")
from app import app
from chirp.testing import TestClient


def csrf(html):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None


def cookie(response):
    for name, value in response.headers:
        if name == "set-cookie" and value.startswith("chirp_session="):
            return value.split(";", 1)[0].partition("=")[2]
    return None


async def exercise():
    async with TestClient(app) as client:
        login_page = await client.get("/login")
        token = csrf(login_page.text)
        session = cookie(login_page)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"chirp_session={session}",
        }

        malformed = await client.post(
            "/login", body=f"_csrf_token={token}".encode(), headers=headers
        )
        authenticated = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={token}".encode(),
            headers=headers,
        )
        auth_session = cookie(authenticated) or session
        full = await client.get(
            "/dashboard", headers={"Cookie": f"chirp_session={auth_session}"}
        )
        fragment = await client.get(
            "/dashboard",
            headers={
                "Cookie": f"chirp_session={auth_session}",
                "HX-Request": "true",
            },
        )

    print(json.dumps({
        "malformed": [malformed.status, "Invalid" in malformed.text],
        "full": [full.status, "<html" in full.text, "Account summary" in full.text],
        "fragment": [
            fragment.status,
            "<html" in fragment.text,
            "Account summary" in fragment.text,
        ],
    }))


asyncio.run(exercise())
"""


@pytest.mark.issue(863)
def test_generated_app_uses_one_page_for_plain_htmx_and_malformed_form_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise sync GET, async POST, full render, and named-block render."""
    project = scaffold(tmp_path, monkeypatch, mode="v2")
    result = run_and_parse(project, _REQUEST_POSTURES)

    assert result.returncode == 0, result.stderr
    assert result.payload == {
        "malformed": [200, True],
        "full": [200, True, True],
        "fragment": [200, False, True],
    }


@pytest.mark.issue(863)
def test_generated_app_fails_loud_for_missing_named_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode="v2")
    result = run_and_parse(
        project,
        """
import json, sys
sys.path.insert(0, ".")
from app import app
from chirp import Fragment

try:
    app.render(Fragment("dashboard/page.html", "missing_response_block"))
except Exception as exc:
    print(json.dumps({"type": type(exc).__name__, "message": str(exc)}))
else:
    print(json.dumps({"type": None, "message": ""}))
""",
    )

    assert result.returncode == 0, result.stderr
    assert result.payload["type"] is not None
    assert "missing_response_block" in result.payload["message"]
