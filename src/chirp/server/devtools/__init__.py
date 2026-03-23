"""Chirp DevTools (⌁⌁) — debug overlay for development mode.

The app injects a single script tag on full-page responses. The script itself
is served from an internal route and is idempotent, so it can be included on
multiple navigations without duplicating listeners or toast containers.

The overlay monitors HTMX requests, SSE connections, View Transitions, render
plans, layout chains, route metadata, DOM diffs, and provides an element inspector.

Shortcuts: Ctrl+Shift+D toggles the drawer; Ctrl+Shift+K toggles the inspector.
Set ``localStorage`` key ``chirp-debug-verbose`` to ``1`` to log boot to console.

Features (v3):

- **Rosettes syntax highlighting**: Highlighted response previews, curl commands,
  and DOM diffs via ``/__chirp/debug/highlight`` endpoint (GET, base64 code).
- **SSE monitor**: EventSource connection lifecycle and event log.
- **Network waterfall**: Inline bars for request timing phases.
- **View Transition tracking**: Hooks ``document.startViewTransition`` lifecycle.
- **DOM diff**: Before/after swap snapshots with unified diff view.
- **Render plan inspector**: Decodes ``X-Chirp-Render-Plan`` header into detail panel.

The JavaScript is split into modules under ``devtools/js/`` and concatenated at
import time into a single IIFE. No build step required.
"""

import html
import json
from importlib.resources import files

DEVTOOLS_BOOT_PATH = "/__chirp/debug/htmx.js"
HIGHLIGHT_PATH = "/__chirp/debug/highlight"

DEVTOOLS_BOOT_SNIPPET = (
    f'<script src="{DEVTOOLS_BOOT_PATH}" data-chirp-debug="htmx" defer></script>'
)

# Backwards-compatible aliases
HTMX_DEBUG_BOOT_PATH = DEVTOOLS_BOOT_PATH
HTMX_DEBUG_BOOT_SNIPPET = DEVTOOLS_BOOT_SNIPPET

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


_JS_LOAD_ORDER = (
    "state",
    "helpers",
    "highlight",
    "collectors",
    "ui",
    "inspector",
    "errors",
)


def _load_devtools_js() -> str:
    """Concatenate JS modules into a single IIFE."""
    js_dir = files("chirp.server.devtools") / "js"
    parts = [
        "(function() {",
        "if (window.__chirpHtmxDebugBooted) return;",
        "window.__chirpHtmxDebugBooted = true;",
        "",
    ]
    for name in _JS_LOAD_ORDER:
        content = (js_dir / f"{name}.js").read_text(encoding="utf-8")
        parts.append(content)
    parts.append("})();")
    return "\n".join(parts)


DEVTOOLS_BOOT_JS = _load_devtools_js()

# Backwards-compatible alias
HTMX_DEBUG_BOOT_JS = DEVTOOLS_BOOT_JS
