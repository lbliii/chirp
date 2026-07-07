"""Published HTTP QUERY compatibility claims stay aligned with #525."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_query_rfc_records_the_implemented_request_contract() -> None:
    text = (_ROOT / "docs/rfcs/009-http-query.md").read_text()
    assert "#525 request contract implemented" in text
    assert "Discovery/`OPTIONS`" in text
    assert "#526-#535" in text


def test_public_docs_keep_query_experimental_and_asgi_only() -> None:
    public_api = (_ROOT / "docs/public-api.md").read_text()
    routes = (_ROOT / "site/content/docs/build-apps/pages-navigation/routes.md").read_text()
    assert 'methods=["QUERY"], query_media_types=(...)' in public_api
    assert "must now add a non-empty `query_media_types=(...)`" in public_api
    assert "Experimental HTTP QUERY routes" in routes
    assert "explicit-route-only" in routes
    assert "fused sync path to ASGI" in routes
    assert 'TestClient.request("QUERY", ...)' in routes
    assert "native forms cannot submit QUERY" in routes
