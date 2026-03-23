"""Backwards-compat test — verify the htmx_debug shim still exports everything."""

from chirp.server.htmx_debug import (
    HIGHLIGHT_PATH,
    HTMX_DEBUG_BOOT_JS,
    HTMX_DEBUG_BOOT_PATH,
    HTMX_DEBUG_BOOT_SNIPPET,
    handle_highlight_request,
    highlight_code,
)


def test_htmx_debug_shim_exports() -> None:
    """All legacy names are importable and non-empty."""
    assert HTMX_DEBUG_BOOT_PATH == "/__chirp/debug/htmx.js"
    assert "script" in HTMX_DEBUG_BOOT_SNIPPET
    assert "__chirpHtmxDebugBooted" in HTMX_DEBUG_BOOT_JS
    assert HIGHLIGHT_PATH == "/__chirp/debug/highlight"
    assert callable(handle_highlight_request)
    assert callable(highlight_code)
