"""HTMX debug bootstrap assets for development mode.

The app injects a single script tag on full-page responses. The script itself
is served from an internal route and is idempotent, so it can be included on
multiple navigations without duplicating listeners or toast containers.

The tray logs HTMX requests with timings (RTT, swap, settle), Chirp response
headers (``X-Chirp-Route-*``, ``X-Chirp-Layout-*``, ``X-Chirp-Render-Intent``,
``X-Request-Id`` when present), and optional element inspector. Shortcuts: Ctrl+Shift+D toggles the
drawer; Ctrl+Shift+K toggles the inspector (opens the drawer if needed). Set
``localStorage`` key ``chirp-debug-verbose`` to ``1`` to log boot to the
console.

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
