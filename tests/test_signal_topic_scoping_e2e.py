"""E2E tests for #317 — runtime topic scoping on signal_connect + lazy sources."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.realtime.signals import DerivedSpec, SignalSpec
from chirp.testing import TestClient


def _topic_scoping_app(
    tmp_path: Path, *, with_prefix: bool = False
) -> tuple[App, dict[str, int], dict[str, int]]:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "home").mkdir()
    (pages / "board").mkdir()

    (pages / "_layout.html").write_text(
        "{# target: body #}\n"
        "{{ signal_connect() }}\n"
        "<div id='shell-chrome'>{{ signal('chrome') }}</div>\n"
        "{% block content %}{% end %}"
    )
    (pages / "home" / "page.py").write_text(
        """
from chirp import Page

def get():
    return Page("home/page.html", "page_content", page_block_name="page_content")
"""
    )
    (pages / "home" / "page.html").write_text(
        '{% block page_content %}<p id="home">home</p>{% end %}'
    )
    (pages / "board" / "page.py").write_text(
        """
from chirp import Page

def get():
    return Page("board/page.html", "page_content", page_block_name="page_content")
"""
    )
    (pages / "board" / "page.html").write_text(
        "{% block page_content %}"
        '<section {{ signal_bind("board_view") }}>board</section>'
        "{% end %}"
    )

    app = App(config=AppConfig(template_dir=pages))

    @app.signal("chrome", initial=lambda: "ok")
    async def chrome_signal():  # pragma: no cover
        if False:
            yield 0

    board_pumped = {"n": 0}
    lobby_pumped = {"n": 0}

    async def board_source():
        board_pumped["n"] += 1
        yield "board"
        await asyncio.sleep(30.0)

    async def lobby_source():
        lobby_pumped["n"] += 1
        yield {"stats": 1}
        await asyncio.sleep(30.0)

    @app.signal("board_feed", source=board_source, initial=lambda: "board")
    async def board_feed():  # pragma: no cover
        if False:
            yield 0

    @app.signal("lobby_feed", source=lobby_source, initial=lambda: {"stats": 0})
    async def lobby_feed():  # pragma: no cover
        if False:
            yield 0

    @app.derived("board_view", on=("board_feed",))
    def board_view(value: str) -> str:
        return value

    @app.derived("lobby_stats", on=("lobby_feed",))
    def lobby_stats(value: dict) -> int:
        return value["stats"]

    app.mount_pages(str(pages))
    if with_prefix:
        app.set_signal_prefix_topics({"/board": ("lobby_stats",)})
    app.freeze()
    return app, board_pumped, lobby_pumped


@pytest.mark.issue(317)
class TestSignalTopicScopingE2E:
    async def test_home_page_scopes_connect_to_shell_topics_only(self, tmp_path: Path) -> None:
        app, board_pumped, lobby_pumped = _topic_scoping_app(tmp_path)
        async with TestClient(app) as client:
            response = await client.get("/home")
        assert response.status == 200
        assert 'sse-connect="/_chirp/live?topics=chrome"' in response.text
        assert "board_feed" not in response.text
        assert "lobby_feed" not in response.text
        assert board_pumped["n"] == 0
        assert lobby_pumped["n"] == 0

    async def test_board_page_includes_derived_source_deps(self, tmp_path: Path) -> None:
        app, _, _ = _topic_scoping_app(tmp_path)
        async with TestClient(app) as client:
            response = await client.get("/board")
        assert response.status == 200
        html = response.text
        assert "topics=" in html
        assert "board_view" in html
        assert "board_feed" in html
        assert "chrome" in html
        assert "lobby_feed" not in html

    async def test_prefix_map_merges_proactive_topics(self, tmp_path: Path) -> None:
        app, _, _ = _topic_scoping_app(tmp_path, with_prefix=True)
        async with TestClient(app) as client:
            response = await client.get("/board")
        assert "lobby_stats" in response.text
        assert "lobby_feed" in response.text

    async def test_scoped_stream_pumps_only_bound_primary_sources(self, tmp_path: Path) -> None:
        app, board_pumped, lobby_pumped = _topic_scoping_app(tmp_path)
        async with TestClient(app) as client:
            await client.get("/home")
            result = await client.sse("/_chirp/live?topics=chrome", max_events=1)
        assert result.status == 200
        assert lobby_pumped["n"] == 0
        assert board_pumped["n"] == 0

        board_pumped["n"] = 0
        async with TestClient(app) as client:
            result = await client.sse("/_chirp/live?topics=board_view,board_feed,chrome", max_events=2)
        assert result.status == 200
        assert board_pumped["n"] >= 1
        assert lobby_pumped["n"] == 0


class TestSignalRegistryTopicHelpers:
    def test_expand_connection_topics_includes_derived_dependencies(self) -> None:
        from chirp.realtime.signals import SignalRegistry

        reg = SignalRegistry()
        reg.register(SignalSpec(name="source"))
        reg.register_derived(DerivedSpec(name="view", deps=("source",), compute=lambda s: s))
        expanded = reg.expand_connection_topics(("view",))
        assert expanded == ("source", "view")

    def test_prefix_topics_use_longest_match(self) -> None:
        from chirp.realtime.signals import SignalRegistry

        reg = SignalRegistry()
        reg.register(SignalSpec(name="a"))
        reg.register(SignalSpec(name="b"))
        reg.set_prefix_topics(
            {
                "/markets": frozenset({"a"}),
                "/markets/trending": frozenset({"b"}),
            }
        )
        assert reg.prefix_topics_for_path("/markets/trending/foo") == frozenset({"b"})
        assert reg.prefix_topics_for_path("/markets/research") == frozenset({"a"})
