"""Executable contract for the canonical complex-search QUERY example."""

from urllib.parse import urlencode

import pytest

from chirp.testing import TestClient, assert_is_fragment

QUERY_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html",
}


def _body(**values: str | list[str]) -> bytes:
    return urlencode(values, doseq=True).encode()


@pytest.mark.issue(534)
async def test_native_get_renders_a_bookmarkable_full_page(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.get("/?q=python&topic=data")

    assert response.status == 200
    assert "<!DOCTYPE html>" in response.text
    assert "Free-Threaded Query Engines" in response.text
    assert 'data-method="GET"' in response.text


@pytest.mark.issue(534)
async def test_get_fallback_ignores_advanced_query_parameters(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.get("/?q=python&min_citations=100000&open_access=1")

    assert response.status == 200
    assert "Hypermedia-Native Python Applications" in response.text
    assert "Free-Threaded Query Engines" in response.text
    assert "<strong>3</strong> papers" in response.text


@pytest.mark.issue(534)
async def test_direct_query_renders_the_full_page_from_the_same_template(example_app) -> None:
    body = _body(
        topics=["web", "security"],
        year_from="2025",
        open_access="1",
        terms="policy\nbrowser caches",
    )
    async with TestClient(example_app) as client:
        response = await client.request("QUERY", "/", headers=QUERY_HEADERS, body=body)

    assert response.status == 200
    assert "<!DOCTYPE html>" in response.text
    assert "Nonce-Safe Conditional HTML" in response.text
    assert "Property Tests for Protocol Parsers" not in response.text
    assert 'data-method="QUERY"' in response.text


@pytest.mark.issue(534)
async def test_enhanced_query_returns_only_the_named_results_block(example_app) -> None:
    headers = {
        **QUERY_HEADERS,
        "HX-Request": "true",
        "HX-Target": "results",
        "HX-Trigger": "search-submit",
    }
    async with TestClient(example_app) as client:
        response = await client.request(
            "QUERY",
            "/",
            headers=headers,
            body=_body(q="faceted", topics=["web", "data"]),
        )

    assert response.status == 200
    assert_is_fragment(response)
    assert response.text.lstrip().startswith('<section id="results"')
    assert "Faceted Search Without a SPA" in response.text
    assert "<html" not in response.text


@pytest.mark.issue(534)
async def test_valid_but_unprocessable_query_returns_validation_error(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.request(
            "QUERY",
            "/",
            headers=QUERY_HEADERS,
            body=_body(year_from="not-a-year"),
        )

    assert response.status == 422
    assert "year_from: Enter a whole number." in response.text
    assert 'id="results"' in response.text


@pytest.mark.issue(534)
async def test_malformed_query_content_fails_with_actionable_400(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.request(
            "QUERY",
            "/",
            headers=QUERY_HEADERS,
            body=b"q=broken%escape",
        )

    assert response.status == 400
    assert "Malformed QUERY body: invalid percent escape" in response.text


@pytest.mark.issue(534)
async def test_empty_and_falsy_results_render_visibly(example_app) -> None:
    async with TestClient(example_app) as client:
        empty = await client.request(
            "QUERY",
            "/",
            headers=QUERY_HEADERS,
            body=_body(q="no-such-paper"),
        )
        zero = await client.get("/?q=deterministic")

    assert empty.status == 200
    assert "<strong>0</strong> papers" in empty.text
    assert "No papers match" in empty.text
    assert "Deterministic HTML Contract Testing" in zero.text
    assert "0 citations" in zero.text


@pytest.mark.issue(534)
def test_example_passes_startup_contract_checks(example_app) -> None:
    example_app.check()
