"""Server-side contract tests for the htmx 2/4 DevTools browser proof."""

from chirp.testing import TestClient


async def test_full_pages_select_each_htmx_runtime(example_app) -> None:
    async with TestClient(example_app) as client:
        htmx2 = await client.get("/")
        htmx4 = await client.get("/v4")
        compat = await client.get("/v4-compat")

    assert "htmx.org@2.0.10" in htmx2.text
    assert "htmx.org@4.0.0-beta5" in htmx4.text
    assert "htmx-2-compat.min.js" not in htmx4.text
    assert "htmx-2-compat.min.js" in compat.text


async def test_htmx_fragment_contains_primary_and_oob_updates(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.fragment(
            "/swap",
            method="POST",
            target="result",
            trigger="swap-button",
        )

    assert response.status == 200
    assert '<div id="result" data-island="lifecycle-probe">' in response.text
    assert 'id="counter" hx-swap-oob="outerHTML"' in response.text
    assert response.header("x-chirp-render-intent") == "fragment"


async def test_htmx4_metadata_normalizes_target_and_source(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.fragment(
            "/inspect",
            method="POST",
            target="div#metadata",
            source="button#inspect-button",
            request_type="partial",
        )

    assert response.status == 200
    assert 'data-target-raw="div#metadata"' in response.text
    assert 'data-target-id="metadata"' in response.text
    assert 'data-source-id="inspect-button"' in response.text
    assert 'data-source-tag="button"' in response.text
    assert 'data-trigger="inspect-button"' in response.text
    assert 'data-request-type="partial"' in response.text
    assert 'data-accept="text/html"' in response.text


async def test_htmx_failure_remains_html_and_actionable(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.fragment(
            "/failure",
            method="POST",
            target="result",
            trigger="failure-button",
        )

    assert response.status == 503
    assert response.content_type.startswith("text/html")
    assert "Server failed" in response.text
