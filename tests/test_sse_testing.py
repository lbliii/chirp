"""Public SSE testing-helper contracts across htmx client dialects."""

import pytest

from chirp import App, AppConfig, EventStream, SSEEvent
from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION
from chirp.testing import TestClient, assert_sse_wired, extract_sse_attrs

pytestmark = pytest.mark.issue(553)


def _htmx4_app(*, partial_target: str = "#status") -> App:
    app = App(AppConfig(htmx=True, htmx_version=HTMX4_PREVIEW_VERSION))

    @app.route("/")
    def index():
        return (
            '<div hx-sse:connect="/events" hx-target="#feed">'
            '<div id="feed">seed</div><div id="status">ready</div></div>'
        )

    @app.route("/events")
    def events():
        async def gen():
            yield SSEEvent(
                data=(
                    f'<hx-partial hx-target="{partial_target}">'
                    "<strong>updated</strong></hx-partial>"
                )
            )

        return EventStream(gen())

    return app


def test_extract_sse_attrs_includes_native_htmx4_connection() -> None:
    connects, swaps = extract_sse_attrs(
        '<div hx-sse:connect="/events" hx-target="#feed"><div id="feed"></div></div>'
    )

    assert connects == ["/events"]
    assert swaps == set()


async def test_assert_sse_wired_validates_htmx4_partial_target() -> None:
    async with TestClient(_htmx4_app()) as client:
        await assert_sse_wired(client, "/", "/events", max_events=1)


async def test_assert_sse_wired_fails_for_missing_htmx4_partial_target() -> None:
    async with TestClient(_htmx4_app(partial_target="#missing")) as client:
        with pytest.raises(AssertionError, match="partial target '#missing'"):
            await assert_sse_wired(client, "/", "/events", max_events=1)


@pytest.mark.issue(544)
async def test_assert_sse_wired_accepts_repeated_signal_selector_targets() -> None:
    app = App(AppConfig(htmx=True, htmx_version=HTMX4_PREVIEW_VERSION))

    @app.route("/")
    def index():
        return (
            '<div hx-sse:connect="/_chirp/live?topics=balance">'
            '<span data-chirp-signal="balance">1</span>'
            '<strong data-chirp-signal="balance">1</strong></div>'
        )

    @app.signal("balance")
    async def balance():
        yield 2

    async with TestClient(app) as client:
        await assert_sse_wired(client, "/", "/_chirp/live?topics=balance", max_events=1)
