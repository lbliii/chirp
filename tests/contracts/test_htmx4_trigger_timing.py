"""Version-aware response timing-header boundary contracts (#549)."""

import pytest

from chirp import App, AppConfig, Response
from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(549)


def _app(response: Response, *, version: str) -> App:
    app = App(
        AppConfig(
            debug=True,
            htmx=True,
            htmx_version=version,
            skip_contract_checks=True,
        )
    )

    @app.route("/")
    def index():
        return response

    return app


@pytest.mark.parametrize(
    ("response", "header", "helper", "lifecycle"),
    [
        (
            Response("swap").with_hx_trigger_after_swap({"saved": {"id": 7}}),
            "HX-Trigger-After-Swap",
            "with_hx_trigger_after_swap",
            "htmx:before:settle",
        ),
        (
            Response("settle").with_hx_trigger_after_settle("saved"),
            "HX-Trigger-After-Settle",
            "with_hx_trigger_after_settle",
            "htmx:after:settle",
        ),
        (
            Response("manual").with_header("hX-tRiGgEr-AfTeR-sWaP", "saved"),
            "HX-Trigger-After-Swap",
            "with_hx_trigger_after_swap",
            "htmx:before:settle",
        ),
    ],
)
async def test_preview_htmx_request_rejects_removed_timing_header_before_send(
    response: Response,
    header: str,
    helper: str,
    lifecycle: str,
) -> None:
    async with TestClient(_app(response, version=HTMX4_PREVIEW_VERSION)) as client:
        result = await client.fragment("/", request_type="partial")

    assert result.status == 500
    assert result.header(header) is None
    assert result.header("vary") == "HX-Request, HX-Request-Type"
    assert header in result.text
    assert helper in result.text
    assert lifecycle in result.text
    assert HTMX4_PREVIEW_VERSION in result.text
    assert "render event data" in result.text


@pytest.mark.parametrize(
    ("response", "header"),
    [
        (Response("swap").with_hx_trigger_after_swap("saved"), "HX-Trigger-After-Swap"),
        (
            Response("settle").with_hx_trigger_after_settle({"saved": True}),
            "HX-Trigger-After-Settle",
        ),
    ],
)
async def test_htmx2_request_preserves_existing_wire_and_merge_semantics(
    response: Response,
    header: str,
) -> None:
    async with TestClient(_app(response, version="2.0.10")) as client:
        result = await client.fragment("/")

    assert result.status == 200
    assert result.header(header) == response.header(header)


async def test_preview_generic_response_preserves_literal_header_and_varies_cache() -> None:
    response = Response("generic").with_hx_trigger_after_settle("saved")
    async with TestClient(_app(response, version=HTMX4_PREVIEW_VERSION)) as client:
        result = await client.get("/")

    assert result.status == 200
    assert result.header("HX-Trigger-After-Settle") == "saved"
    assert result.header("vary") == "HX-Request, HX-Request-Type"


async def test_preview_receipt_phase_trigger_remains_portable() -> None:
    response = Response("portable").with_hx_trigger({"saved": {"id": 7}})
    async with TestClient(_app(response, version=HTMX4_PREVIEW_VERSION)) as client:
        result = await client.fragment("/", request_type="partial")

    assert result.status == 200
    assert result.header("HX-Trigger") == response.header("HX-Trigger")
