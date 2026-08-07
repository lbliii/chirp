"""Issue #859: UI-neutral shell actions + hypermedia handoff contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from kida.environment.exceptions import TemplateNotFoundError

from chirp import (
    AnnouncementHandoff,
    App,
    AppConfig,
    FocusHandoff,
    Fragment,
    HypermediaHandoff,
    Page,
    Response,
    ShellAction,
    ShellActions,
    ShellActionZone,
    TitleHandoff,
    apply_handoff,
)
from chirp.ext.chirp_ui import use_chirp_ui
from chirp.http.handoff import (
    ANNOUNCEMENTS_ELEMENT_ID,
    CHIRP_FOCUS_EVENT,
    announce_oob_html,
    title_oob_html,
)
from chirp.http.request import Request
from chirp.pages.shell_actions import ShellActionsRenderer, shell_actions_fragment
from chirp.server.negotiation import negotiate
from chirp.shell_actions import (
    SHELL_ACTIONS_CHIRPUI_TEMPLATE,
    SHELL_ACTIONS_TARGET,
    SHELL_ACTIONS_TEMPLATE,
)
from chirp.templating.integration import create_environment, render_fragment
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(859)


def _boosted_request(path: str = "/page") -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [
                (b"hx-request", b"true"),
                (b"hx-boosted", b"true"),
                (b"hx-target", b"main"),
            ],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


def _actions() -> ShellActions:
    return ShellActions(
        primary=ShellActionZone(
            items=(
                ShellAction(id="new", label="New item", href="/new"),
                ShellAction(
                    id="save",
                    label="Save",
                    kind="form",
                    form_action="/save",
                    hidden_fields=(("id", "1"),),
                    hx_post="/save",
                    hx_target="#toast",
                    hx_swap="innerHTML",
                ),
            )
        ),
        overflow=ShellActionZone(
            items=(ShellAction(id="archive", label="Archive", href="/archive"),)
        ),
    )


@pytest.fixture
def neutral_env(tmp_path: Path):
    """Kida env with Chirp macros only — no chirp-ui PackageLoader."""
    (tmp_path / "page.html").write_text(
        '<main id="main" tabindex="-1">'
        '{% block content %}<div id="page-content">Hello</div>{% end %}'
        "</main>",
        encoding="utf-8",
    )
    # create_environment ambient-loads chirp-ui when installed. For the
    # neutral contract we still use it (chirp-ui may be present), but the
    # default renderer must not *import* chirpui templates.
    return create_environment(AppConfig(template_dir=tmp_path), filters={}, globals_={}), tmp_path


class TestNeutralShellActionsRender:
    def test_default_renderer_is_chirp_template_not_chirpui(self) -> None:
        frag = shell_actions_fragment(_actions())
        assert frag is not None
        template, block, target = frag
        assert template == SHELL_ACTIONS_TEMPLATE
        assert "chirpui" not in template
        assert block == "content"
        assert target == SHELL_ACTIONS_TARGET

    def test_neutral_oob_html_has_no_chirpui_classes(self, neutral_env) -> None:
        env, _ = neutral_env
        html = render_fragment(
            env,
            Fragment(SHELL_ACTIONS_TEMPLATE, "content", shell_actions=_actions()),
        )
        assert "data-chirp-shell-actions" in html
        assert 'data-chirp-shell-zone="primary"' in html
        assert 'href="/new"' in html
        assert "New item" in html
        assert 'action="/save"' in html
        assert "chirpui-" not in html
        assert "chirpui/" not in html

    def test_boosted_navigation_appends_neutral_shell_actions_oob(self, neutral_env) -> None:
        env, tmp_path = neutral_env
        (tmp_path / "page.html").write_text(
            '{% block content %}<div id="page-content">Body</div>{% end %}',
            encoding="utf-8",
        )
        result = negotiate(
            Page("page.html", "content", shell_actions=_actions()),
            kida_env=env,
            request=_boosted_request(),
        )
        assert 'id="chirp-shell-actions"' in result.text
        assert 'hx-swap-oob="innerHTML"' in result.text
        assert 'href="/new"' in result.text
        assert "chirpui-" not in result.text

    def test_boosted_navigation_clears_shell_actions_when_missing(self, neutral_env) -> None:
        env, tmp_path = neutral_env
        (tmp_path / "page.html").write_text(
            '{% block content %}<div id="page-content">Body</div>{% end %}',
            encoding="utf-8",
        )
        result = negotiate(
            Page("page.html", "content"),
            kida_env=env,
            request=_boosted_request(),
        )
        assert 'id="chirp-shell-actions"' in result.text
        assert 'hx-swap-oob="innerHTML"></div>' in result.text

    def test_explicit_renderer_override_without_replacing_transport(self, neutral_env) -> None:
        env, tmp_path = neutral_env
        custom = tmp_path / "chirp"
        custom.mkdir()
        (custom / "custom_actions.html").write_text(
            "{% fragment content %}"
            '<div data-app-renderer="1">{{ shell_actions.primary.items[0].label }}</div>'
            "{% end %}",
            encoding="utf-8",
        )
        renderer = ShellActionsRenderer(template="chirp/custom_actions.html", block="content")
        frag = shell_actions_fragment(_actions(), renderer)
        assert frag == ("chirp/custom_actions.html", "content", SHELL_ACTIONS_TARGET)
        html = render_fragment(
            env,
            Fragment(frag[0], frag[1], shell_actions=_actions()),
        )
        assert 'data-app-renderer="1"' in html
        assert "New item" in html

    def test_missing_custom_renderer_template_fails_loud(self, neutral_env) -> None:
        env, _ = neutral_env
        with pytest.raises(TemplateNotFoundError):
            render_fragment(
                env,
                Fragment("chirp/does-not-exist.html", "content", shell_actions=_actions()),
            )


class TestChirpUICompatibilityAdapter:
    def test_use_chirp_ui_registers_chirpui_renderer(self, tmp_path: Path) -> None:
        app = App(AppConfig(template_dir=tmp_path, debug=True, skip_contract_checks=True))
        use_chirp_ui(app)
        renderer = app._mutable_state.shell_actions_renderer
        assert isinstance(renderer, ShellActionsRenderer)
        assert renderer.template == SHELL_ACTIONS_CHIRPUI_TEMPLATE


class TestHypermediaHandoff:
    def test_title_and_announce_oob_markup(self) -> None:
        title = title_oob_html(TitleHandoff(title="Projects"))
        assert 'id="chirpui-document-title"' in title
        assert 'hx-swap-oob="true"' in title
        assert "Projects" in title

        announce = announce_oob_html(AnnouncementHandoff(message="Saved"))
        assert f'id="{ANNOUNCEMENTS_ELEMENT_ID}"' in announce
        assert 'aria-live="polite"' in announce
        assert 'hx-swap-oob="innerHTML"' in announce
        assert "Saved" in announce

    def test_apply_handoff_sets_focus_title_history_and_announcement(self) -> None:
        response = apply_handoff(
            Response(body='<div id="page-content">ok</div>'),
            HypermediaHandoff(
                focus=FocusHandoff(target="#page-heading", fallback="#main"),
                title=TitleHandoff(title="Dashboard", push_url="/dashboard"),
                announcement=AnnouncementHandoff(message="Loaded dashboard"),
            ),
        )
        assert response.header("HX-Push-Url") == "/dashboard"
        settle = response.header("HX-Trigger-After-Settle")
        assert settle is not None
        payload = json.loads(settle)
        assert CHIRP_FOCUS_EVENT in payload
        assert payload[CHIRP_FOCUS_EVENT]["target"] == "#page-heading"
        assert payload[CHIRP_FOCUS_EVENT]["fallback"] == "#main"
        assert 'id="chirpui-document-title"' in response.text
        assert "Dashboard" in response.text
        assert "Loaded dashboard" in response.text
        assert f'id="{ANNOUNCEMENTS_ELEMENT_ID}"' in response.text

    def test_title_oob_escapes_html(self) -> None:
        html = title_oob_html("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestHandoffFullPlainAndHtmxPaths:
    async def test_full_page_and_htmx_fragment_with_shell_actions(self, tmp_path: Path) -> None:
        pages = tmp_path / "pages"
        pages.mkdir()
        (pages / "_layout.html").write_text(
            "<!DOCTYPE html><html><head>"
            '<title id="chirpui-document-title">{{ page_title ?? "App" }}</title>'
            '{% from "chirp/handoff.html" import live_region, handoff_runtime_script %}'
            '{% from "chirp/macros/shell_actions.html" import shell_actions_bar %}'
            "{{ handoff_runtime_script() }}"
            "</head><body>"
            "{{ live_region() }}"
            '<div id="chirp-shell-actions">'
            "{% if shell_actions is defined %}{{ shell_actions_bar(shell_actions) }}{% end %}"
            "</div>"
            '<main id="main" tabindex="-1" hx-boost="true" hx-target="#main" '
            'hx-swap="innerHTML" hx-select="#page-content">'
            '<div id="page-content">{% block content %}{% end %}</div>'
            "</main></body></html>",
            encoding="utf-8",
        )
        (pages / "_context.py").write_text(
            "from chirp import ShellAction, ShellActions, ShellActionZone\n"
            "def context():\n"
            "    return {\n"
            "        'page_title': 'Home',\n"
            "        'shell_actions': ShellActions(\n"
            "            primary=ShellActionZone(\n"
            "                items=(ShellAction(id='go', label='Go', href='/go'),)\n"
            "            )\n"
            "        ),\n"
            "    }\n",
            encoding="utf-8",
        )
        (pages / "page.py").write_text(
            "from chirp import Page\n"
            "def handler():\n"
            "    return Page('page.html', 'content', page_block_name='content')\n",
            encoding="utf-8",
        )
        (pages / "page.html").write_text(
            '{% block content %}<h1 id="page-heading">Home</h1>{% end %}',
            encoding="utf-8",
        )

        app = App(AppConfig(template_dir=str(pages), debug=True, skip_contract_checks=True))
        app.mount_pages(str(pages))

        async with TestClient(app) as client:
            full = await client.get("/")
            assert full.status == 200
            assert 'id="chirp-announcements"' in full.text
            assert 'data-chirp="handoff"' in full.text
            assert 'src="/_chirp/handoff.js"' in full.text
            assert "Go" in full.text
            assert "chirpui-shell-actions" not in full.text

            frag = await client.fragment(
                "/",
                headers={"HX-Boosted": "true", "HX-Target": "main"},
            )
            assert frag.status == 200
            assert 'id="chirp-shell-actions"' in frag.text
            assert 'hx-swap-oob="innerHTML"' in frag.text
            assert "Go" in frag.text
            assert "chirpui-" not in frag.text

            js = await client.get("/_chirp/handoff.js")
            assert js.status == 200
            assert b"chirp:focus" in js.body_bytes
            # CSP posture: external script, not an inline handler attribute.
            assert b"hx-on::" not in js.body_bytes


class TestMissingBlocksAndCspPosture:
    def test_handoff_runtime_is_external_script_marker(self, neutral_env) -> None:
        env, _ = neutral_env
        html = env.from_string(
            '{% from "chirp/handoff.html" import handoff_runtime_script %}'
            "{{ handoff_runtime_script() }}"
        ).render()
        assert 'src="/_chirp/handoff.js"' in html
        assert 'data-chirp="handoff"' in html
        assert "onclick=" not in html
        assert "hx-on::" not in html
