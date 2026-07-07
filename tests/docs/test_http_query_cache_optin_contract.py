"""Published HTTP QUERY cache opt-in claims stay aligned with #531."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.issue(531)

_ROOT = Path(__file__).parents[2]


def test_rfc_records_explicit_default_off_cache_lifecycle() -> None:
    rfc = (_ROOT / "docs" / "rfcs" / "009-http-query.md").read_text()
    assert "#531 explicit cache opt-in implemented" in rfc
    assert "`CacheMiddleware(query_key_func=...)` is the sole experimental opt-in" in rfc
    assert "#531 cache lifecycle receipt" in rfc
    assert "No `AppConfig` field was added" in rfc


def test_user_docs_keep_config_managed_query_caching_disabled() -> None:
    routes = (
        _ROOT / "site" / "content" / "docs" / "build-apps" / "pages-navigation" / "routes.md"
    ).read_text()
    forum = (_ROOT / "docs" / "deployment" / "forum-production.md").read_text()
    assert "`AppConfig(cache_middleware_enabled=True)` remain GET-only" in routes
    assert "configuration-managed caching remains GET-only" in forum
