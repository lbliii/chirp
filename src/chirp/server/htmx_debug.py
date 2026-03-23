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

Features (v3):

- **Rosettes syntax highlighting**: Highlighted response previews, curl commands,
  and DOM diffs via ``/__chirp/debug/highlight`` endpoint (GET, base64 code).
- **SSE monitor**: EventSource connection lifecycle and event log.
- **Network waterfall**: Inline SVG bars for request timing phases.
- **View Transition tracking**: Hooks ``document.startViewTransition`` lifecycle.
- **DOM diff**: Before/after swap snapshots with unified diff view.
- **Render plan inspector**: Decodes ``X-Chirp-Render-Plan`` header into detail panel.

The script lives in htmx_debug.js (not embedded in Python) to avoid
Python string escaping footguns when editing JavaScript.
"""

import html
import json
from importlib.resources import files

HTMX_DEBUG_BOOT_PATH = "/__chirp/debug/htmx.js"
HIGHLIGHT_PATH = "/__chirp/debug/highlight"

HTMX_DEBUG_BOOT_SNIPPET = (
    f'<script src="{HTMX_DEBUG_BOOT_PATH}" data-chirp-debug="htmx" defer></script>'
)

_HAS_ROSETTES = False
try:
    from rosettes import highlight as _rosettes_highlight
    from rosettes import supports_language as _rosettes_supports

    _HAS_ROSETTES = True
except ImportError:
    pass


def highlight_code(code: str, language: str) -> str:
    """Highlight code via Rosettes if available, else return HTML-escaped ``<pre>``."""
    if _HAS_ROSETTES and _rosettes_supports(language):
        return _rosettes_highlight(code, language)
    escaped = html.escape(code)
    return f'<pre class="chirp-hl-fallback"><code>{escaped}</code></pre>'


def handle_highlight_request(query_params: dict[str, str]) -> str:
    """Handle GET /__chirp/debug/highlight — returns JSON ``{"html": "..."}``."""
    import base64

    raw = query_params.get("code", "")
    try:
        code = base64.b64decode(raw).decode("utf-8")
    except Exception:
        code = raw
    language = query_params.get("lang", "text")
    highlighted = highlight_code(code, language)
    return json.dumps({"html": highlighted})


def _load_htmx_debug_js() -> str:
    return (files("chirp.server") / "htmx_debug.js").read_text(encoding="utf-8")


HTMX_DEBUG_BOOT_JS = _load_htmx_debug_js()
