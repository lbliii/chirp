"""HTML injection middleware.

Injects a snippet (e.g. a ``<script>`` tag) into every ``text/html``
response before a configurable target string (default: ``</body>``).

Useful for live-reload scripts, analytics, debug toolbars, or any
markup that should appear on every page without modifying templates.
"""

import hashlib
import logging
import os
import re
from collections.abc import Callable
from dataclasses import replace

import anyio
import anyio.to_thread

from chirp.http.request import Request
from chirp.http.response import FileResponse, Response, StreamingResponse
from chirp.middleware.csp_nonce import csp_nonce
from chirp.middleware.protocol import AnyResponse, Next
from chirp.middleware.streaming_html import async_stream_inject_before_body
from chirp.server.sender import _format_http_date

_LOG = logging.getLogger("chirp.middleware.inject")

_SCRIPT_CHIRP_MARKER = re.compile(
    r"""<script\b[^>]*\bdata-chirp=["']([^"']+)["']""",
    re.IGNORECASE,
)


def _html_has_script_chirp_marker(html: str, chirp_value: str) -> bool:
    """True when a ``<script>`` tag carries ``data-chirp="<value>"``.

    Substring dedup on ``data-chirp="alpine"`` alone false-positives when page
    content mentions the marker (docs, examples). Anchor to script tags (#191).
    """
    return any(match.group(1) == chirp_value for match in _SCRIPT_CHIRP_MARKER.finditer(html))


async def _materialize_html_file(
    response: FileResponse,
) -> tuple[Response, float] | tuple[FileResponse, None]:
    """Read a ``text/html`` FileResponse off disk into a buffered Response.

    Snippet injection needs the whole body, so a static HTML page served by
    :class:`~chirp.middleware.static.StaticFiles` is read into memory and
    returned as a :class:`~chirp.http.response.Response` that the existing
    body-injection path can rewrite. Status, headers, cookies, content type
    and render intent are preserved.

    Returns ``(response, mtime)`` where *mtime* is the file's POSIX
    modification time, captured alongside the read so the caller can preserve
    ``Last-Modified`` and rebuild conditional-GET headers over the
    **post-injection** body (the on-disk size+mtime ETag no longer describes
    the served bytes once a snippet is inserted — see :func:`_finalize_html`).

    Non-HTML FileResponses (CSS, images, large binaries) and unreadable files
    are returned unchanged (with ``mtime=None``) so they keep streaming from
    disk via :func:`~chirp.server.sender.send_file_response`, which retains
    full ETag / Last-Modified / Range support.
    """
    if not response.resolved_content_type.startswith("text/html"):
        return response, None

    def _read() -> tuple[bytes, float]:
        # stat + read in the same worker call so Last-Modified reflects the
        # bytes we actually read (one extra stat vs the sender's; acceptable).
        st = os.stat(response.path)
        return response.path.read_bytes(), st.st_mtime

    try:
        raw, mtime = await anyio.to_thread.run_sync(_read)
    except OSError:
        _LOG.warning("HTMLInject: could not read %s for injection", response.path)
        return response, None
    buffered = Response(
        body=raw.decode("utf-8", errors="replace"),
        status=response.status,
        content_type=response.resolved_content_type,
        headers=response.headers,
        cookies=response.cookies,
        render_intent=response.render_intent,
    )
    return buffered, mtime


def _finalize_html(
    response: Response,
    *,
    mtime: float | None,
    stable: bool,
) -> Response:
    """Attach conditional-GET headers to an injected static-HTML Response.

    PR #190 made :class:`StaticFiles` emit a streaming :class:`FileResponse`
    with ETag / Last-Modified / 304 / Range. When an inject middleware
    materializes that file to rewrite its body, the response goes through the
    buffered :func:`~chirp.server.sender.send_response`, which has no
    conditional-GET awareness — so caching was silently lost (#198).

    This recomputes caching over the **post-injection** bytes:

    * **Last-Modified** is preserved from the file's *mtime* (the snippet does
      not change the file on disk).
    * **ETag** is recomputed only when the injected snippet is *stable* (the
      same for every request — i.e. nonce-free). A per-request CSP nonce makes
      the served bytes vary, so emitting a stable ETag would let a cache serve
      a body carrying a dead nonce; in that case we emit ``Last-Modified`` only
      and never a 304 (no false cache hits). The stable ETag is a content hash
      of the injected body so it changes when either the file or the snippet
      changes.
    * Final conditional evaluation happens once, after the complete middleware
      chain, so a later CSP nonce rewrite can suppress unsafe ``304`` reuse.
    * **Range / Accept-Ranges is intentionally dropped** for injected HTML:
      on-disk byte offsets shift once a snippet is inserted, so a Range against
      the file would return wrong bytes. Clients fall back to a full 200.
      Verbatim (non-injected) files keep full Range via ``send_file_response``.

    ``mtime is None`` means the response was not a materialized static file
    (a normal handler Response, or an unreadable/non-HTML file) — return it
    untouched so dynamic responses keep their existing (cache-less) behavior.
    """
    if mtime is None or response.status != 200:
        return response

    last_modified = _format_http_date(mtime)

    # When the served bytes are NOT stable (per-request nonce), we cannot offer
    # any validator that would let a cache reuse this body — a 304 (by ETag or
    # by Last-Modified) would serve a body carrying a dead nonce. Emit
    # Last-Modified for diagnostics only and never short-circuit to 304.
    if not stable:
        return replace(response, headers=(*response.headers, ("Last-Modified", last_modified)))

    digest = hashlib.blake2b(response.body_bytes, digest_size=16).hexdigest()
    etag = f'"{digest}"'
    extra = (("Last-Modified", last_modified), ("ETag", etag))
    return replace(response, headers=(*response.headers, *extra))


class HTMLInject:
    """Middleware that injects HTML content into text/html responses.

    Affects ``Response`` objects whose ``content_type`` contains
    ``text/html`` and ``text/html`` :class:`~chirp.http.response.FileResponse`
    bodies (static HTML pages served by :class:`StaticFiles`), which are read
    from disk, injected, and returned as a buffered ``Response`` — snippet
    injection inherently needs the whole body, so streaming is moot here.
    ``StreamingResponse`` and ``SSEResponse`` are passed through unchanged
    (see :class:`StreamingHTMLInject` / :class:`AlpineInject` for streaming
    HTML).

    When *full_page_only* is ``True``, the snippet is injected **only**
    when the *before* target string is found in the response body.
    When ``False`` (the default), the snippet is appended at the end
    if the target string is absent.

    **Per-request snippet factories.** *snippet* may be a plain string **or** a
    *factory* — ``Callable[[str], str]`` taking the live per-request CSP nonce
    and returning the snippet. A factory is resolved inside request scope from
    :func:`chirp.middleware.csp_nonce.csp_nonce` (empty string when nonces are
    disabled), so an inline ``<script>`` it builds carries the live ``nonce``
    attribute and survives a nonce-only CSP that no longer ships
    ``'unsafe-inline'``. Every framework inline-script injection (safe_target,
    sse_lifecycle, delegation, view_transitions, islands, speculation_rules,
    Alpine) passes a factory so its inline script is nonced per request; a plain
    string is still accepted for back-compat and treated as a constant factory.

    Usage::

        app.add_middleware(HTMLInject(
            lambda nonce: f'<script nonce="{nonce}">…</script>',
            before="</body>",
        ))
    """

    __slots__ = ("_full_page_only", "_skip_htmx", "_snippet", "_snippet_factory", "_target")

    def __init__(
        self,
        snippet: str | Callable[[str], str],
        *,
        before: str = "</body>",
        full_page_only: bool = False,
        skip_htmx: bool = False,
    ) -> None:
        if isinstance(snippet, str):
            self._snippet_factory: Callable[[str], str] = lambda _nonce: snippet
            self._snippet = snippet
        else:
            self._snippet_factory = snippet
            # Keep ``_snippet`` as a nonce-less rendering for introspection;
            # injection always goes through :meth:`_render_snippet`.
            self._snippet = snippet("")
        self._target = before
        self._full_page_only = full_page_only
        self._skip_htmx = skip_htmx

    def _render_snippet(self) -> str:
        """Build the snippet with the live request CSP nonce.

        ``csp_nonce()`` returns the per-request nonce when CSP nonces are enabled
        and an empty string otherwise (never raises). A plain-string snippet is
        wrapped in a constant factory at construction time, so this returns the
        verbatim string for legacy callers.
        """
        return self._snippet_factory(csp_nonce())

    def _snippet_is_stable(self) -> bool:
        """Whether the snippet is identical for every request (nonce-free).

        Renders the factory with two distinct sentinel nonces; a stable snippet
        ignores the nonce and produces identical output. Only stable snippets
        may carry a conditional ETag (see :func:`_finalize_html`) — a snippet
        that embeds the per-request CSP nonce varies per request, so caching it
        with a strong validator would serve a body with a dead nonce.
        """
        return self._snippet_factory("\x00chirp-a") == self._snippet_factory("\x00chirp-b")

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Inject the snippet into HTML responses."""
        response = await next(request)

        # Static HTML files (FileResponse) are read into a buffered Response so
        # the snippet can be injected; non-HTML files stream through untouched.
        mtime: float | None = None
        if isinstance(response, FileResponse):
            response, mtime = await _materialize_html_file(response)
        # Only modify concrete Response objects with HTML content
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if self._skip_htmx and request.is_htmx:
            return response
        # Prefer explicit render intent when available. Fall back to
        # request heuristics for unknown/legacy responses.
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response

        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        snippet = self._render_snippet()
        if self._target in body:
            body = body.replace(self._target, snippet + self._target, 1)
            stable = self._snippet_is_stable()
        elif self._full_page_only:
            # No injection performed: served bytes equal the file bytes (stable).
            return _finalize_html(response, mtime=mtime, stable=True)
        else:
            body = body + snippet
            stable = self._snippet_is_stable()

        return _finalize_html(replace(response, body=body), mtime=mtime, stable=stable)


class StreamingHTMLInject(HTMLInject):
    """HTMLInject variant that also rewrites full-page StreamingResponse HTML.

    Inherits the per-request snippet-factory support from :class:`HTMLInject`:
    both the buffered and streaming paths resolve the snippet from the live
    request nonce, so a factory-built inline script is nonced on either path.
    """

    __slots__ = ("_dedup_marker",)

    def __init__(
        self,
        snippet: str | Callable[[str], str],
        *,
        before: str = "</body>",
        full_page_only: bool = False,
        dedup_marker: str | None = None,
        skip_htmx: bool = False,
    ) -> None:
        super().__init__(
            snippet,
            before=before,
            full_page_only=full_page_only,
            skip_htmx=skip_htmx,
        )
        self._dedup_marker = dedup_marker

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if isinstance(response, StreamingResponse):
            return self._streaming(response, request)
        mtime: float | None = None
        if isinstance(response, FileResponse):
            response, mtime = await _materialize_html_file(response)
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if self._skip_htmx and request.is_htmx:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if self._dedup_marker and self._dedup_marker in body:
            return _finalize_html(response, mtime=mtime, stable=True)
        snippet = self._render_snippet()
        if self._target in body:
            body = body.replace(self._target, snippet + self._target, 1)
            stable = self._snippet_is_stable()
        elif self._full_page_only:
            return _finalize_html(response, mtime=mtime, stable=True)
        else:
            body = body + snippet
            stable = self._snippet_is_stable()
        return _finalize_html(replace(response, body=body), mtime=mtime, stable=stable)

    def _streaming(self, response: StreamingResponse, request: Request) -> StreamingResponse:
        if "text/html" not in response.content_type:
            return response
        if self._skip_htmx and request.is_htmx:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        # Read the live nonce here, in request scope — the chunk generator drains
        # later, but the snippet string is fixed up front from the live nonce.
        new_chunks = async_stream_inject_before_body(
            response.chunks,
            snippet=self._render_snippet(),
            before=self._target,
            dedup_marker=self._dedup_marker,
            full_page_only=self._full_page_only,
        )
        return replace(response, chunks=new_chunks)


class AlpineInject(HTMLInject):
    """HTMLInject that also rewrites streaming HTML and skips on dedup.

    Checks for ``data-chirp="alpine"`` in the response body before injecting.
    This prevents double-loading when the document already includes Alpine
    from another source.

    The Alpine bootstrap contains one inline ``<script>`` (the ``safeData``
    helper); the plugin/core tags are external ``src=`` references. To survive a
    nonce-based CSP that no longer ships ``'unsafe-inline'``, that inline script
    must carry the **live per-request nonce**, which the base-class snippet
    factory (``Callable[[str], str]``, resolved from
    :func:`chirp.middleware.csp_nonce.csp_nonce`) provides.

    For :class:`~chirp.http.response.StreamingResponse` (e.g. ``Suspense``),
    the same per-request snippet is inserted before the first ``</body>`` using
    a bounded buffer so ``</body>`` may be split across chunks. The nonce is read
    in :meth:`_alpine_streaming`, which runs in request scope (the streaming
    chunks drain later, but the snippet string is fixed up front from the live
    nonce here).
    """

    __slots__ = ()

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if isinstance(response, StreamingResponse):
            return self._alpine_streaming(response, request)
        mtime: float | None = None
        if isinstance(response, FileResponse):
            response, mtime = await _materialize_html_file(response)
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if _html_has_script_chirp_marker(body, "alpine"):
            return _finalize_html(response, mtime=mtime, stable=True)
        # Reuse the fetched response — do not call ``next`` again via super().
        target = self._target
        snippet = self._render_snippet()
        if target in body:
            body = body.replace(target, snippet + target, 1)
            stable = self._snippet_is_stable()
        elif self._full_page_only:
            return _finalize_html(response, mtime=mtime, stable=True)
        else:
            body = body + snippet
            stable = self._snippet_is_stable()
        return _finalize_html(replace(response, body=body), mtime=mtime, stable=stable)

    def _alpine_streaming(self, response: StreamingResponse, request: Request) -> StreamingResponse:
        if "text/html" not in response.content_type:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        # Read the live nonce here, in request scope — the chunk generator drains
        # later, but the snippet string is fixed up front from the live nonce.
        new_chunks = async_stream_inject_before_body(
            response.chunks,
            snippet=self._render_snippet(),
            before=self._target,
            dedup_script_chirp="alpine",
            full_page_only=self._full_page_only,
        )
        return replace(response, chunks=new_chunks)


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
        if response.render_intent == "unknown" and request.is_htmx:
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
                "htmx navigations will not animate. Set AppConfig(view_transitions=True) "
                "for htmx swap transitions, or 'full' for cross-document transitions."
            )
        return response
