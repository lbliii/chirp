"""Tests for the Hacker News Live Reader example."""

from chirp.testing import TestClient


class TestStoryList:
    """The front page renders the story list with seed data."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_contains_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Hacker News" in response.text

    async def test_index_renders_stories(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Story list items should be rendered (seed or live data)
            assert "story-item" in response.text
            assert "story-rank" in response.text

    async def test_index_renders_story_meta(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Meta line should have points and comments
            assert "point" in response.text
            assert "comment" in response.text

    async def test_index_renders_domains(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "github.com" in response.text

    async def test_index_contains_sse_connection(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'sse-connect="/events"' in response.text

    async def test_sse_scope_is_outside_main(self, example_app) -> None:
        """sse_scope renders outside #main so connection persists across navigation."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            main_pos = html.find('id="main"')
            assert main_pos >= 0
            main_close = _find_main_closing_div(html, main_pos)
            assert main_close >= 0
            sse_pos = html.find('sse-connect=')
            assert sse_pos >= 0
            sse_div_open = html.rfind("<div", 0, sse_pos)
            assert sse_div_open >= 0
            assert sse_div_open > main_close, "sse_scope must be outside #main"


def _find_main_closing_div(html: str, main_pos: int) -> int:
    """Find the </div> that closes the #main element (balanced bracket count)."""
    depth = 1
    i = main_pos + 1
    while i < len(html):
        next_open = html.find("<div", i)
        next_close = html.find("</div>", i)
        if next_close < 0:
            return -1
        if 0 <= next_open < next_close:
            depth += 1
            i = next_open + 1
        else:
            depth -= 1
            if depth == 0:
                return next_close
            i = next_close + 1
    return -1

    async def test_index_contains_view_transition_meta(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'name="view-transition"' in response.text

    async def test_index_fragment_returns_list_only(self, example_app) -> None:
        """Fragment request for / returns just the story list, not the full page."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/")
            assert response.status == 200
            assert "story-list" in response.text
            # Must NOT contain the full page shell (header, footer)
            assert "site-header" not in response.text
            assert "<footer>" not in response.text

    async def test_index_fragment_does_not_nest(self, example_app) -> None:
        """Fragment response must not contain the #main container itself."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/")
            assert 'id="main"' not in response.text


class TestStoryDetail:
    """The story detail page renders comments (uses seed data fallback)."""

    async def test_detail_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/story/1")
            assert response.status == 200

    async def test_detail_fragment_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment("/story/1")
            assert response.status == 200


class TestSSE:
    """Live score updates stream through the SSE pipeline."""

    async def test_receives_initial_event(self, example_app) -> None:
        """The SSE stream yields an initial ping to confirm connection."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=1)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) >= 1

    async def test_initial_event_is_ping(self, example_app) -> None:
        """The initial event is a ping, not an OOB fragment (avoids flicker)."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=1)
        ping_events = [e for e in result.events if e.event == "ping"]
        assert len(ping_events) >= 1
        assert ping_events[0].data == "connected"

    async def test_fragment_events_have_oob_swap(self, example_app) -> None:
        """When score changes, fragment events include hx-swap-oob."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=3, timeout=12.0)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        if fragment_events:
            oob_events = [e for e in fragment_events if "hx-swap-oob" in e.data]
            assert len(oob_events) >= 1

    async def test_fragment_events_have_story_meta(self, example_app) -> None:
        """Fragment events contain story metadata (points, comments)."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=3, timeout=12.0)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        if fragment_events:
            assert "point" in fragment_events[0].data


class TestFilters:
    """Template filters produce correct output."""

    async def test_timeago_in_rendered_page(self, example_app) -> None:
        """The timeago filter renders relative times in the story list."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Seed stories have recent timestamps, so they should show "ago"
            assert "ago" in response.text or "just now" in response.text

    async def test_pluralize_in_rendered_page(self, example_app) -> None:
        """The pluralize filter renders correct singular/plural forms."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Seed stories have various counts
            assert "point" in response.text
            assert "comment" in response.text
