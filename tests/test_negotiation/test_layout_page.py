"""Tests for LayoutPage slot context and boosted navigation."""

from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.config import AppConfig
from chirp.http.request import Request
from chirp.pages.shell_actions import ShellAction, ShellActions, ShellActionZone
from chirp.server.negotiation import negotiate
from chirp.templating.integration import create_environment
from chirp.templating.returns import LayoutPage, LayoutSuspense, Suspense, Template


class TestLayoutPageSlotContext:
    """Integration test: page vars in nested macro slots via LayoutPage negotiation.

    Mirrors Dori skills page: container → stack → form from chirpui-style
    templates. If selected_tags/all_tags are undefined in the form slot,
    negotiation would raise UndefinedError. This test ensures the full
    Chirp negotiation path (LayoutPage, render_block, FileSystemLoader)
    propagates context into slot bodies.
    """

    def test_layout_page_slot_context_inheritance(self, kida_env: Environment) -> None:
        """selected_tags and all_tags in nested slots render without UndefinedError."""
        result = negotiate(
            LayoutPage(
                "skills/page.html",
                "page_content",
                q="search",
                selected_tags=["a", "b"],
                all_tags=["a", "b", "c"],
            ),
            kida_env=kida_env,
        )
        assert result.status == 200
        assert "a,b" in result.text
        assert "abc" in result.text
        assert 'action="/skills"' in result.text
        assert "Skills" in result.text

    def test_layout_page_boosted_navigation_appends_shell_actions_oob(
        self,
        kida_env_with_packages: Environment,
    ) -> None:
        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/skills",
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

        result = negotiate(
            LayoutPage(
                "skills/page.html",
                "page_content",
                shell_actions=ShellActions(
                    primary=ShellActionZone(
                        items=(ShellAction(id="new-skill", label="New skill", href="/skills/new"),)
                    )
                ),
                q="search",
                selected_tags=["a", "b"],
                all_tags=["a", "b", "c"],
            ),
            kida_env=kida_env_with_packages,
            request=request,
        )

        assert result.render_intent == "fragment"
        assert 'id="chirp-shell-actions"' in result.text
        assert 'hx-swap-oob="innerHTML"' in result.text
        assert 'href="/skills/new"' in result.text

    def test_layout_page_boosted_navigation_clears_shell_actions_when_missing(
        self,
        kida_env_with_packages: Environment,
    ) -> None:
        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/skills",
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

        result = negotiate(
            LayoutPage(
                "skills/page.html",
                "page_content",
                q="search",
                selected_tags=["a", "b"],
                all_tags=["a", "b", "c"],
            ),
            kida_env=kida_env_with_packages,
            request=request,
        )

        assert 'id="chirp-shell-actions"' in result.text
        assert 'hx-swap-oob="innerHTML"></div>' in result.text

    def test_template_extending_chirpui_app_shell_layout_renders(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "page.html").write_text(
            '{% extends "chirpui/app_shell_layout.html" %}'
            "{% block brand %}Shell App{% end %}"
            "{% block sidebar %}"
            '{% from "chirpui/sidebar.html" import sidebar, sidebar_link, sidebar_section %}'
            "{% call sidebar() %}"
            '{% call sidebar_section("Main") %}'
            '{{ sidebar_link("/", "Home") }}'
            "{% end %}"
            "{% end %}"
            "{% end %}"
            "{% block content %}<div>Hello shell</div>{% end %}",
            encoding="utf-8",
        )
        env = create_environment(
            AppConfig(template_dir=tmp_path), filters={}, globals_={"shell_actions": None}
        )

        result = negotiate(Template("page.html"), kida_env=env)

        assert result.status == 200
        assert "Shell App" in result.text
        assert "Hello shell" in result.text
        assert 'class="chirpui-app-shell' in result.text

    def test_template_extending_chirpui_app_shell_layout_keeps_collapsible_override(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "page.html").write_text(
            '{% extends "chirpui/app_shell_layout.html" %}'
            "{% block sidebar_collapsible %}true{% end %}"
            "{% block brand %}Shell App{% end %}"
            "{% block content %}<div>Hello shell</div>{% end %}",
            encoding="utf-8",
        )
        env = create_environment(
            AppConfig(template_dir=tmp_path), filters={}, globals_={"shell_actions": None}
        )

        result = negotiate(Template("page.html"), kida_env=env)

        assert result.status == 200
        assert "chirpui-app-shell" in result.text
        assert "Hello shell" in result.text

    @pytest.mark.asyncio
    async def test_layout_suspense_boosted_navigation_appends_shell_actions_oob(
        self,
        tmp_path: Path,
    ) -> None:
        from chirp.http.response import StreamingResponse
        from chirp.pages.types import LayoutChain, LayoutInfo

        (tmp_path / "dashboard.html").write_text(
            "<h1>{{ title }}</h1>"
            '<div id="stats">{% block stats %}'
            "{% if stats %}<p>{{ stats[0] }}</p>{% else %}<p>Loading stats...</p>{% end %}"
            "{% end %}</div>",
            encoding="utf-8",
        )
        (tmp_path / "_layout.html").write_text(
            "{# target: body #}"
            '<html><body><div id="chirp-shell-actions"></div><main id="main">{% block content %}{% end %}</main></body></html>',
            encoding="utf-8",
        )
        env = create_environment(AppConfig(template_dir=tmp_path), filters={}, globals_={})

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/dashboard",
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

        async def _stats():
            return ["ready"]

        result = negotiate(
            LayoutSuspense(
                Suspense("dashboard.html", title="Dashboard", stats=_stats()),
                LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),)),
                context={
                    "shell_actions": ShellActions(
                        primary=ShellActionZone(
                            items=(ShellAction(id="deploy", label="Deploy", href="/deploy"),)
                        )
                    )
                },
                request=request,
            ),
            kida_env=env,
            request=request,
        )

        assert isinstance(result, StreamingResponse)
        chunks = [chunk async for chunk in result.chunks]
        combined = "".join(chunks)
        assert "Loading stats..." in combined
        assert 'id="chirp-shell-actions"' in combined
        assert 'hx-swap-oob="innerHTML"' in combined
        assert 'href="/deploy"' in combined

    def test_layout_page_boosted_navigation_prefers_page_block_name(self, tmp_path: Path) -> None:
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        (tmp_path / "base.html").write_text(
            '{% block page_root %}<section class="page-root">{% block panel %}{% endblock %}</section>{% endblock %}'
        )
        (tmp_path / "child.html").write_text(
            '{% extends "base.html" %}{% block panel %}<div id="panel">{{ body }}</div>{% endblock %}'
        )

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/child",
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

        result = negotiate(
            LayoutPage("child.html", "panel", page_block_name="page_root", body="Hello"),
            kida_env=env,
            request=request,
        )

        assert result.render_intent == "fragment"
        assert 'class="page-root"' in result.text
        assert 'id="panel"' in result.text
        assert "Hello" in result.text

    def test_layout_page_non_boosted_fragment_keeps_fragment_block(self, tmp_path: Path) -> None:
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        (tmp_path / "base.html").write_text(
            '{% block page_root %}<section class="page-root">{% block panel %}{% endblock %}</section>{% endblock %}'
        )
        (tmp_path / "child.html").write_text(
            '{% extends "base.html" %}{% block panel %}<div id="panel">{{ body }}</div>{% endblock %}'
        )

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/child",
                "headers": [
                    (b"hx-request", b"true"),
                    (b"hx-target", b"panel"),
                ],
                "query_string": b"",
                "http_version": "1.1",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive=_receive,
        )

        result = negotiate(
            LayoutPage("child.html", "panel", page_block_name="page_root", body="Hello"),
            kida_env=env,
            request=request,
        )

        assert result.render_intent == "fragment"
        assert 'id="panel"' in result.text
        assert "Hello" in result.text
        assert 'class="page-root"' not in result.text
