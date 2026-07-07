"""Published HTTP QUERY cache claims stay aligned with #530."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.issue(530)

_ROOT = Path(__file__).parents[2]


def test_query_rfc_records_key_inputs_lifecycle_and_measurement() -> None:
    rfc = (_ROOT / "docs" / "rfcs" / "009-http-query.md").read_text()
    assert "#530 cache-key design implemented" in rfc
    assert "chirp:query:v1:<digest>" in rfc
    assert "reads through `Request.body()`" in rfc
    assert "#530 synthetic cost and memory receipt" in rfc
    assert "This is a synthetic implementation receipt" in rfc


def test_query_user_docs_keep_cache_default_off() -> None:
    routes = (
        _ROOT / "site" / "content" / "docs" / "build-apps" / "pages-navigation" / "routes.md"
    ).read_text()
    forum = (_ROOT / "docs" / "deployment" / "forum-production.md").read_text()
    assert "`CacheMiddleware` still bypasses QUERY" in routes
    assert "it does not enable cache reads or writes" in routes
    assert "`CacheMiddleware` bypasses QUERY responses by default" in forum
