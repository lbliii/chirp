"""Tests for LayoutPage slot context and boosted navigation."""

import time
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

    Mirrors a skills page pattern: container → stack → form from chirpui-style
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
            AppConfig(template_dir=tmp_path),
            filters={},
            globals_={"shell_actions": None, "csrf_token": lambda: "test-csrf"},
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
            AppConfig(template_dir=tmp_path),
            filters={},
            globals_={"shell_actions": None, "csrf_token": lambda: "test-csrf"},
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
            "{% if stats is deferred %}<p>Loading stats...</p>{% else %}<p>{{ stats[0] }}</p>{% end %}"
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

    @pytest.mark.asyncio
    async def test_layout_suspense_boosted_navigation_appends_layout_oob_blocks(
        self,
        tmp_path: Path,
    ) -> None:
        """Layout OOB blocks (sidebar, breadcrumbs) must appear as OOB swaps
        in LayoutSuspense streaming responses during boosted navigation."""
        from chirp.http.response import StreamingResponse
        from chirp.pages.types import LayoutChain, LayoutInfo
        from chirp.templating.oob_registry import OOBRegionConfig, OOBRegistry

        (tmp_path / "page.html").write_text(
            "<h1>{{ title }}</h1>"
            '<div id="data">{% block data %}'
            "{% if data is deferred %}<p>Loading...</p>{% else %}<p>{{ data }}</p>{% end %}"
            "{% end %}</div>",
            encoding="utf-8",
        )
        (tmp_path / "_layout.html").write_text(
            "{# target: body #}\n"
            "<html><body>\n"
            '<nav id="sidebar-nav">\n'
            '{% region sidebar_oob(current_path="/") %}\n'
            '<a class="{{ "active" if current_path == "/about" else "" }}">About</a>\n'
            "{% end %}\n"
            "</nav>\n"
            '<main id="main">{% block content %}{% end %}</main></body></html>',
            encoding="utf-8",
        )
        env = create_environment(AppConfig(template_dir=tmp_path), filters={}, globals_={})

        oob_registry = OOBRegistry()
        oob_registry.register(
            "sidebar_oob", OOBRegionConfig(target_id="sidebar-nav", swap="innerHTML", wrap=True)
        )
        oob_registry.freeze()

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/about",
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

        async def _data():
            return "resolved"

        result = negotiate(
            LayoutSuspense(
                Suspense("page.html", title="About", data=_data()),
                LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),)),
                context={"current_path": "/about"},
                request=request,
            ),
            kida_env=env,
            request=request,
            oob_registry=oob_registry,
        )

        assert isinstance(result, StreamingResponse)
        chunks = [chunk async for chunk in result.chunks]
        combined = "".join(chunks)
        assert 'id="sidebar-nav"' in combined
        assert 'hx-swap-oob="innerHTML"' in combined
        assert 'class="active"' in combined

    @pytest.mark.asyncio
    async def test_layout_suspense_boosted_navigation_omit_outer_layouts_skips_layouts(
        self,
        tmp_path: Path,
    ) -> None:
        from chirp.http.response import StreamingResponse
        from chirp.pages.types import LayoutChain, LayoutInfo
        from chirp.templating.fragment_target_registry import FragmentTargetRegistry

        (tmp_path / "page.html").write_text(
            "<h1>{{ title }}</h1>"
            '<div id="data">{% block data %}'
            "{% if data is deferred %}<p>Loading...</p>{% else %}<p>{{ data }}</p>{% end %}"
            "{% end %}</div>",
            encoding="utf-8",
        )
        (tmp_path / "_layout.html").write_text(
            "{# target: body #}\n"
            "{# outlet: site-content #}\n"
            "<!DOCTYPE html><html><body>"
            '<div id="site-content">{% block content %}{% end %}</div>'
            "</body></html>",
            encoding="utf-8",
        )
        env = create_environment(AppConfig(template_dir=tmp_path), filters={}, globals_={})

        fragment_target_registry = FragmentTargetRegistry()
        fragment_target_registry.register(
            "site-content",
            fragment_block="content",
            omit_outer_layouts=True,
        )
        fragment_target_registry.freeze()

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/about",
                "headers": [
                    (b"hx-request", b"true"),
                    (b"hx-boosted", b"true"),
                    (b"hx-target", b"site-content"),
                ],
                "query_string": b"",
                "http_version": "1.1",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive=_receive,
        )

        async def _data():
            return "resolved"

        result = negotiate(
            LayoutSuspense(
                Suspense("page.html", title="About", data=_data()),
                LayoutChain(
                    layouts=(
                        LayoutInfo("_layout.html", "body", 0, outlet_target_id="site-content"),
                    )
                ),
                request=request,
            ),
            kida_env=env,
            request=request,
            fragment_target_registry=fragment_target_registry,
        )

        assert isinstance(result, StreamingResponse)
        chunks = [chunk async for chunk in result.chunks]
        combined = "".join(chunks)
        assert "<!DOCTYPE html>" not in combined
        assert 'id="site-content"' not in combined
        assert "<h1>About</h1>" in combined
        assert "resolved" in combined

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


class TestLayoutSuspenseChainedOOBOffLoop:
    """The OOB streams chained onto LayoutSuspense must render off the loop (#193).

    ``append_layout_oob_stream`` and ``append_shell_actions_oob_stream`` each run
    a discrete CPU-bound layout render. If that render runs inline on the loop the
    LayoutSuspense path stalls concurrent tasks even though the shell body and
    layout wrap already run off-loop.
    """

    @staticmethod
    async def _count_ticks_during(coro_factory):
        """Drain a stream while a ticker counts loop iterations."""
        import anyio

        counter = {"n": 0}

        async def ticker() -> None:
            while True:
                counter["n"] += 1
                await anyio.sleep(0.002)

        chunks: list[str] = []
        async with anyio.create_task_group() as tg:
            tg.start_soon(ticker)
            chunks = [chunk async for chunk in coro_factory()]
            tg.cancel_scope.cancel()
        return chunks, counter["n"]

    @pytest.mark.asyncio
    async def test_chained_layout_oob_stream_does_not_block_loop(
        self,
        tmp_path: Path,
    ) -> None:
        """A heavy layout OOB block render does not freeze a concurrent ticker."""
        from chirp.http.response import StreamingResponse
        from chirp.pages.types import LayoutChain, LayoutInfo
        from chirp.templating.oob_registry import OOBRegionConfig, OOBRegistry

        # Page body is trivial; the blocking work lives in the layout OOB region.
        (tmp_path / "page.html").write_text(
            "<h1>{{ title }}</h1>"
            '<div id="data">{% block data %}'
            "{% if data is deferred %}<p>Loading...</p>{% else %}<p>{{ data }}</p>{% end %}"
            "{% end %}</div>",
            encoding="utf-8",
        )
        (tmp_path / "_layout.html").write_text(
            "{# target: body #}\n"
            "<html><body>\n"
            '<nav id="sidebar-nav">\n'
            '{% region sidebar_oob(current_path="/") %}\n'
            "{{ heavy() }}"
            '<a class="{{ "active" if current_path == "/about" else "" }}">About</a>\n'
            "{% end %}\n"
            "</nav>\n"
            '<main id="main">{% block content %}{% end %}</main></body></html>',
            encoding="utf-8",
        )

        def heavy() -> str:
            # Blocking sleep stands in for CPU-bound layout OOB compilation.
            time.sleep(0.2)
            return ""

        env = create_environment(
            AppConfig(template_dir=tmp_path), filters={}, globals_={"heavy": heavy}
        )

        oob_registry = OOBRegistry()
        oob_registry.register(
            "sidebar_oob", OOBRegionConfig(target_id="sidebar-nav", swap="innerHTML", wrap=True)
        )
        oob_registry.freeze()

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/about",
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

        async def _data():
            return "resolved"

        result = negotiate(
            LayoutSuspense(
                Suspense("page.html", title="About", data=_data()),
                LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),)),
                context={"current_path": "/about"},
                request=request,
            ),
            kida_env=env,
            request=request,
            oob_registry=oob_registry,
        )

        assert isinstance(result, StreamingResponse)
        chunks, ticks = await self._count_ticks_during(lambda: result.chunks)
        combined = "".join(chunks)
        # Chained layout OOB swap actually emitted (heavy block rendered).
        assert 'id="sidebar-nav"' in combined
        assert 'hx-swap-oob="innerHTML"' in combined
        assert 'class="active"' in combined
        assert ticks > 10, f"loop appears blocked during chained layout OOB render: ticks={ticks}"
