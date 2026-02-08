"""HTML injection middleware.

Injects a snippet (e.g. a ``<script>`` tag) into every ``text/html``
response before a configurable target string (default: ``</body>``).

Useful for live-reload scripts, analytics, debug toolbars, or any
markup that should appear on every page without modifying templates.
"""

from dataclasses import replace

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next


class HTMLInject:
    """Middleware that injects HTML content into text/html responses.

    Only affects ``Response`` objects whose ``content_type`` contains
    ``text/html``.  ``StreamingResponse`` and ``SSEResponse`` are
    passed through unchanged.

    Usage::

        app.add_middleware(HTMLInject(
            '<script src="/__reload.js"></script>',
            before="</body>",
        ))
    """

    __slots__ = ("_snippet", "_target")

    def __init__(self, snippet: str, *, before: str = "</body>") -> None:
        self._snippet = snippet
        self._target = before

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Inject the snippet into HTML responses."""
        response = await next(request)

        # Only modify concrete Response objects with HTML content
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response

        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        if self._target in body:
            body = body.replace(self._target, self._snippet + self._target, 1)
        else:
            body = body + self._snippet

        return replace(response, body=body)
