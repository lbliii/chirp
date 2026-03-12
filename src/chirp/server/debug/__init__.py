"""Self-contained debug error page renderer.

Re-exports render_debug_page and test-imported helpers for backward compatibility.
"""

from chirp.server.debug.editor import _editor_url
from chirp.server.debug.frames import (
    _collapse_framework_frames,
    _extract_frames,
    _is_app_frame,
)
from chirp.server.debug.renderers import render_debug_page
from chirp.server.debug.request_context import _extract_request_context
from chirp.server.debug.template_context import _extract_template_context

__all__ = [
    "_collapse_framework_frames",
    "_editor_url",
    "_extract_frames",
    "_extract_request_context",
    "_extract_template_context",
    "_is_app_frame",
    "render_debug_page",
]
