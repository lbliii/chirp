"""Tests for native debug runtime wiring."""

import json

import pytest

from chirp import App, AppConfig
from chirp.errors import ConfigurationError
from chirp.realtime.events import EventStream
from chirp.server.debug_runtime import DEBUG_MANIFEST_PATH, DEBUG_TRACES_PATH
from chirp.server.dev_browser_reload import DEV_RELOAD_SSE_PATH
from chirp.server.devtools import DEVTOOLS_BOOT_PATH, HIGHLIGHT_PATH
from chirp.server.fragment_dispatch import FRAGMENT_ROUTE_PREFIX
from chirp.server.fragment_targets_debug import FRAGMENT_TARGETS_DEBUG_PATH
from chirp.server.route_explorer import ROUTE_EXPLORER_PATH
from chirp.testing import TestClient


def test_snapshot_exposes_native_debug_wiring() -> None:
    app = App(AppConfig(debug=True))

    @app.route("/")
    def index():
        return "ok"

    app._ensure_frozen()
    snapshot = app._contract_check_snapshot()

    paths = {route.path for route in snapshot.debug_wiring.routes}
    assert DEVTOOLS_BOOT_PATH in paths
    assert DEBUG_MANIFEST_PATH in paths
    assert DEBUG_TRACES_PATH in paths
    assert any(
        feature.name == "devtools" and feature.enabled for feature in snapshot.debug_wiring.features
    )


@pytest.mark.parametrize(
    "path",
    [
        DEVTOOLS_BOOT_PATH,
        HIGHLIGHT_PATH,
        FRAGMENT_TARGETS_DEBUG_PATH,
        DEBUG_MANIFEST_PATH,
        DEBUG_TRACES_PATH,
        ROUTE_EXPLORER_PATH,
        DEV_RELOAD_SSE_PATH,
        FRAGMENT_ROUTE_PREFIX,
        f"{FRAGMENT_ROUTE_PREFIX}/page.html/content",
    ],
)
def test_reserved_internal_routes_fail_at_freeze(path: str) -> None:
    app = App()

    @app.route(path)
    def internal_collision():
        return "bad"

    with pytest.raises(ConfigurationError, match="reserved internal runtime URL space"):
        app._ensure_frozen()


async def test_debug_manifest_endpoint_is_internal() -> None:
    app = App(AppConfig(debug=True))

    @app.route("/")
    def index():
        return "ok"

    async with TestClient(app) as client:
        response = await client.get(DEBUG_MANIFEST_PATH)

    assert response.status == 200
    assert response.header("X-Chirp-Internal") == "true"
    assert response.header("X-Chirp-Internal-Owner") == "devtools"
    payload = json.loads(response.text)
    assert any(route["path"] == DEVTOOLS_BOOT_PATH for route in payload["routes"])
    assert any(feature["name"] == "devtools" for feature in payload["features"])


async def test_native_sse_traces_capture_user_eventstream() -> None:
    app = App(AppConfig(debug=True))

    @app.route("/events")
    def events():
        async def gen():
            yield "alpha"

        return EventStream(gen())

    async with TestClient(app) as client:
        await client.sse("/events", max_events=1)
        response = await client.get(DEBUG_TRACES_PATH)

    payload = json.loads(response.text)
    phases = [record["phase"] for record in payload["records"]]
    assert "start" in phases
    assert "event" in phases
    assert "closed" in phases
    assert {record["internal"] for record in payload["records"]} == {False}


async def test_internal_dev_reload_sse_traces_are_hidden_by_default() -> None:
    app = App(AppConfig(debug=True, dev_browser_reload=True))

    @app.route("/")
    def index():
        return "ok"

    async with TestClient(app) as client:
        await client.sse(DEV_RELOAD_SSE_PATH, disconnect_after=0.1)
        visible = await client.get(DEBUG_TRACES_PATH)
        internal = await client.get(f"{DEBUG_TRACES_PATH}?internal=1")

    visible_payload = json.loads(visible.text)
    internal_payload = json.loads(internal.text)
    assert visible_payload["records"] == []
    assert any(
        record["owner"] == "dev_browser_reload" and record["internal"]
        for record in internal_payload["records"]
    )
