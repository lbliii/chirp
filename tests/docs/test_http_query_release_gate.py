"""Published HTTP QUERY adoption claims stay aligned with issue #535."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.issue(535)

_ROOT = Path(__file__).resolve().parents[2]
_GUIDE = _ROOT / "docs" / "http-query.md"
_SITE_GUIDE = (
    _ROOT / "site" / "content" / "docs" / "build-apps" / "pages-navigation" / "http-query.md"
)


def test_query_guides_publish_the_same_experimental_boundary() -> None:
    for path in (_GUIDE, _SITE_GUIDE):
        text = path.read_text()
        compact = " ".join(text.split())
        assert "experimental early-adopter" in compact.lower()
        assert "Stable promotion" in compact
        assert "native" in compact
        assert "forms cannot submit QUERY" in compact
        assert "TestClient.query()" in compact
        assert "accepts exactly one" in compact
        assert 'request("QUERY", ...)' in compact
        assert "There is no `TestClient.query()`" not in compact
        assert 'body=b"category=books&year=2026"' in compact
        assert "content=b" not in compact
        assert "filesystem `query()`" in compact
        assert "configuration-managed caching remains get-only" in compact.lower()
        assert "Never rewrite QUERY to POST" in compact
        assert "certifies no CDN" in compact


def test_query_release_gate_names_every_open_promotion_blocker() -> None:
    text = _GUIDE.read_text()

    for issue in ("#527", "#528", "#533", "#534"):
        assert issue in text
    assert "The experimental release gate is met; the stable promotion gate is not" in text
    assert "production-ready QUERY" in text
    assert "uv run ruff check ." in text
    assert "uv run ruff format . --check" in text
    assert "uv run ty check src/chirp/" in text
    assert "uv run pytest" in text


def test_readme_and_public_api_do_not_overclaim_query_support() -> None:
    readme = (_ROOT / "README.md").read_text()
    compact_readme = " ".join(readme.split())
    public_api = (_ROOT / "docs" / "public-api.md").read_text()
    rfc = (_ROOT / "docs" / "rfcs" / "009-http-query.md").read_text()

    assert "Experimental HTTP QUERY" in readme
    assert "stable promotion and universal proxy/CDN support are **not** claimed" in compact_readme
    assert "Literal Fetch" in public_api
    assert "normalized media ranges" in public_api
    assert "RouteDoc.query_media_types" in public_api
    assert "canonical complex-search example" in public_api
    assert "configuration-managed caching remains GET-only" in public_api
    assert "#535 experimental release decision documented" in rfc
    assert "Stable or first-class promotion is not approved" in rfc
    assert "complete static wiring diagnostics (#533) remain open" not in rfc


def test_query_site_navigation_links_the_adoption_guide() -> None:
    index = (
        _ROOT / "site" / "content" / "docs" / "build-apps" / "pages-navigation" / "_index.md"
    ).read_text()
    routes = (
        _ROOT / "site" / "content" / "docs" / "build-apps" / "pages-navigation" / "routes.md"
    ).read_text()

    assert "[[docs/build-apps/pages-navigation/http-query|Experimental HTTP QUERY]]" in index
    assert "[[docs/build-apps/pages-navigation/http-query|Experimental HTTP QUERY]]" in routes
