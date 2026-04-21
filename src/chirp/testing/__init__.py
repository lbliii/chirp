"""Test utilities for chirp applications.

Provides a test client, fragment assertions, htmx header assertions,
and SSE testing helpers.  All public names are re-exported here for
backwards compatibility::

    from chirp.testing import TestClient, assert_is_fragment
"""

from chirp.testing.assertions import (
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_hx_push_url,
    assert_hx_redirect,
    assert_hx_reswap,
    assert_hx_retarget,
    assert_hx_trigger,
    assert_is_error_fragment,
    assert_is_fragment,
    assert_mutation_fragments,
    assert_mutation_redirect,
    assert_oob_targets,
    assert_status,
    hx_headers,
)
from chirp.testing.client import TestClient
from chirp.testing.sse import SSETestResult, assert_sse_wired, extract_sse_attrs

__all__ = [
    "SSETestResult",
    "TestClient",
    "assert_fragment_contains",
    "assert_fragment_not_contains",
    "assert_hx_push_url",
    "assert_hx_redirect",
    "assert_hx_reswap",
    "assert_hx_retarget",
    "assert_hx_trigger",
    "assert_is_error_fragment",
    "assert_is_fragment",
    "assert_mutation_fragments",
    "assert_mutation_redirect",
    "assert_oob_targets",
    "assert_sse_wired",
    "assert_status",
    "extract_sse_attrs",
    "hx_headers",
]
