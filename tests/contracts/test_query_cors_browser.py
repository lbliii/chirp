"""Real-browser same-origin and cross-origin HTTP QUERY proof (#532)."""

from __future__ import annotations

import pytest
from pounce.testing import TestServer

from tests.interop.query_app import QUERY_MEDIA_TYPE, make_probe_app

sync_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = sync_api.Error
sync_playwright = sync_api.sync_playwright
pytestmark = pytest.mark.issue(532)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"Chromium not installed for Playwright: {exc}")
        try:
            yield chromium
        finally:
            chromium.close()


def _fetch_query(page, url: str, body: str) -> dict[str, object]:
    return page.evaluate(
        """async ({url, body, contentType}) => {
          try {
            const response = await fetch(url, {
              method: "QUERY",
              headers: {"Content-Type": contentType},
              body
            });
            return {ok: response.ok, status: response.status, body: await response.text()};
          } catch (error) {
            return {ok: false, status: 0, error: String(error)};
          }
        }""",
        {"url": url, "body": body, "contentType": QUERY_MEDIA_TYPE},
    )


def test_browser_fetch_query_same_origin_and_cors_preflight(browser) -> None:
    source_app, _ = make_probe_app()
    with TestServer(source_app) as source:
        destination_app, destination_state = make_probe_app(cors_origin=source.url)
        with TestServer(destination_app) as destination:
            page = browser.new_page()
            try:
                page.goto(destination.url)
                same_origin = _fetch_query(page, "/query", "facet=same-origin")
                assert same_origin["status"] == 200
                assert 'data-method="QUERY"' in str(same_origin["body"])

                page.goto(source.url)
                cross_origin = _fetch_query(
                    page,
                    f"{destination.url}/query",
                    "facet=cross-origin",
                )
                assert cross_origin["status"] == 200
                assert 'data-method="QUERY"' in str(cross_origin["body"])
            finally:
                page.close()

    assert [item.body for item in destination_state.seen] == [
        b"facet=same-origin",
        b"facet=cross-origin",
    ]
    assert destination_state.mutations == 0


def test_browser_blocks_cross_origin_query_when_cors_omits_method(browser) -> None:
    source_app, _ = make_probe_app()
    with TestServer(source_app) as source:
        destination_app, destination_state = make_probe_app(
            cors_origin=source.url,
            cors_allows_query=False,
        )
        with TestServer(destination_app) as destination:
            page = browser.new_page()
            try:
                page.goto(source.url)
                result = _fetch_query(page, f"{destination.url}/query", "facet=blocked")
            finally:
                page.close()

    assert result["status"] == 0
    assert "Failed to fetch" in str(result["error"])
    assert destination_state.seen == []
    assert destination_state.mutations == 0
