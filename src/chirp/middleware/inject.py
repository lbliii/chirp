"""HTML injection middleware.

Injects a snippet (e.g. a ``<script>`` tag) into every ``text/html``
response before a configurable target string (default: ``</body>``).

Useful for live-reload scripts, analytics, debug toolbars, or any
markup that should appear on every page without modifying templates.
"""

import logging
from dataclasses import replace

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next

_LOG = logging.getLogger("chirp.middleware.inject")


class HTMLInject:
    """Middleware that injects HTML content into text/html responses.

    Only affects ``Response`` objects whose ``content_type`` contains
    ``text/html``.  ``StreamingResponse`` and ``SSEResponse`` are
    passed through unchanged.

    When *full_page_only* is ``True``, the snippet is injected **only**
    when the *before* target string is found in the response body.
    When ``False`` (the default), the snippet is appended at the end
    if the target string is absent.

    Usage::

        app.add_middleware(HTMLInject(
            '<script src="/__reload.js"></script>',
            before="</body>",
        ))
    """

    __slots__ = ("_full_page_only", "_snippet", "_target")

    def __init__(
        self,
        snippet: str,
        *,
        before: str = "</body>",
        full_page_only: bool = False,
    ) -> None:
        self._snippet = snippet
        self._target = before
        self._full_page_only = full_page_only

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Inject the snippet into HTML responses."""
        response = await next(request)

        # Only modify concrete Response objects with HTML content
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        # Prefer explicit render intent when available. Fall back to
        # request heuristics for unknown/legacy responses.
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_fragment:
            return response

        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        if self._target in body:
            body = body.replace(self._target, self._snippet + self._target, 1)
        elif self._full_page_only:
            return response
        else:
            body = body + self._snippet

        return replace(response, body=body)


class ViewTransitionCssDebugWarning:
    """Log when the response body uses View Transition CSS but VT injection is off.

    Only runs in debug builds (see ``compiler._collect_builtin_middleware``).
    Helps catch ``view-transition-name`` / ``@view-transition`` in templates while
    ``AppConfig.view_transitions`` is ``False``, which disables HTMX global VT.
    """

    __slots__ = ()

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_fragment:
            return response

        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        lowered = body.lower()
        if (
            "@view-transition" in lowered
            or "view-transition-name" in lowered
            or "::view-transition" in lowered
        ):
            _LOG.warning(
                "View Transition CSS detected in HTML but view_transitions is disabled — "
                "HTMX navigations will not animate. Set AppConfig(view_transitions=True)."
            )
        return response
