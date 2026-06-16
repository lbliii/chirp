"""Test utilities for chirp applications.

Provides a test client, fragment assertions, htmx header assertions,
and SSE testing helpers.  All public names are re-exported here for
backwards compatibility::

    from chirp.testing import TestClient, assert_is_fragment
"""

from chirp.testing.assertions import (
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_has_id,
    assert_hx_push_url,
    assert_hx_redirect,
    assert_hx_reswap,
    assert_hx_retarget,
    assert_hx_trigger,
    assert_is_error_fragment,
    assert_is_fragment,
    assert_is_full_page,
    assert_mutation_fragments,
    assert_mutation_redirect,
    assert_no_full_document,
    assert_oob_targets,
    assert_status,
    hx_headers,
)
from chirp.testing.browser_smoke import (
    assert_alpine_booted,
    assert_zero_console_errors,
    attach_console_capture,
    filter_console_errors,
    require_playwright,
)
from chirp.testing.chunks import CapturedStream
from chirp.testing.client import TestClient
from chirp.testing.link_crawl import (
    LinkCrawlResult,
    assert_link_integrity,
    crawl_links,
    same_origin_paths,
)
from chirp.testing.route_smoke import RouteSmokeCase, assert_route_smoke
from chirp.testing.sse import SSETestResult, assert_sse_wired, extract_sse_attrs

__all__ = [
    "CapturedStream",
    "LinkCrawlResult",
    "RouteSmokeCase",
    "SSETestResult",
    "TestClient",
    "assert_alpine_booted",
    "assert_fragment_contains",
    "assert_fragment_not_contains",
    "assert_has_id",
    "assert_hx_push_url",
    "assert_hx_redirect",
    "assert_hx_reswap",
    "assert_hx_retarget",
    "assert_hx_trigger",
    "assert_is_error_fragment",
    "assert_is_fragment",
    "assert_is_full_page",
    "assert_link_integrity",
    "assert_mutation_fragments",
    "assert_mutation_redirect",
    "assert_no_full_document",
    "assert_oob_targets",
    "assert_route_smoke",
    "assert_sse_wired",
    "assert_status",
    "assert_zero_console_errors",
    "attach_console_capture",
    "crawl_links",
    "extract_sse_attrs",
    "filter_console_errors",
    "hx_headers",
    "require_playwright",
    "same_origin_paths",
]
