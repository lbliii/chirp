"""Backwards-compatibility shim — re-exports from ``chirp.server.devtools``.

All new code should import from ``chirp.server.devtools`` directly.
This module exists so existing imports continue to work.
"""

from chirp.server.devtools import (  # noqa: F401
    DEVTOOLS_BOOT_JS,
    DEVTOOLS_BOOT_PATH,
    DEVTOOLS_BOOT_SNIPPET,
    HIGHLIGHT_PATH,
    HTMX_DEBUG_BOOT_JS,
    HTMX_DEBUG_BOOT_PATH,
    HTMX_DEBUG_BOOT_SNIPPET,
    handle_highlight_request,
    highlight_code,
)
