"""Published QUERY discovery and response claims stay aligned with #526."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_rfc_records_query_response_matrix_and_remaining_gates() -> None:
    text = (_ROOT / "docs/rfcs/009-http-query.md").read_text()
    assert "#526 response contract implemented" in text
    assert "Executable response matrix (#526)" in text
    assert "test_chirp_preserves_query_redirect_status_and_location" in text
    assert "#527/#528/#533/#534" in text
    assert "#535 records the experimental release decision" in text


def test_site_documents_discovery_opaque_urls_and_client_boundary() -> None:
    text = (_ROOT / "site/content/docs/build-apps/pages-navigation/routes.md").read_text()
    assert "Discovery, redirects, and validators" in text
    assert "explicit `OPTIONS` route, which always wins" in text
    assert "must be opaque" in text
    assert "prefer `307` or `308`" in text
    assert "own paging or" in text
