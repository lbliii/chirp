"""Self-contained debug error page renderer.

Backward-compatible shim. Implementation lives in chirp.server.debug.
"""

from chirp.server.debug import (
    _collapse_framework_frames,
    _editor_url,
    _extract_frames,
    _extract_request_context,
    _extract_template_context,
    _is_app_frame,
    render_debug_page,
)

__all__ = [
    "_collapse_framework_frames",
    "_editor_url",
    "_extract_frames",
    "_extract_request_context",
    "_extract_template_context",
    "_is_app_frame",
    "render_debug_page",
]
