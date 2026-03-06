"""HTMX debug bootstrap assets for development mode.

The app injects a single script tag on full-page responses. The script itself
is served from an internal route and is idempotent, so it can be included on
multiple navigations without duplicating listeners or toast containers.

The script lives in htmx_debug.js (not embedded in Python) to avoid
Python string escaping footguns when editing JavaScript.
"""

from importlib.resources import files

HTMX_DEBUG_BOOT_PATH = "/__chirp/debug/htmx.js"

HTMX_DEBUG_BOOT_SNIPPET = (
    f'<script src="{HTMX_DEBUG_BOOT_PATH}" data-chirp-debug="htmx" defer></script>'
)


def _load_htmx_debug_js() -> str:
    return (files("chirp.server") / "htmx_debug.js").read_text(encoding="utf-8")


HTMX_DEBUG_BOOT_JS = _load_htmx_debug_js()
