"""Block-fetch dispatcher — URL-addressable blocks for any route.

GET ``/_frag{path}?_b={block}`` matches the underlying route for ``{path}``,
invokes its handler, and returns only the named kida block. Makes every block
of every page a first-class, cache-friendly resource without requiring the
handler to know about fragment addressing.

**URL scheme** (RFC 0.2):

- ``/_frag/`` prefix is reserved and collision-checked at ``app.check()`` time.
- Block name is a query param ``_b`` so the ``{path:path}`` doesn't swallow it.
- Trailing-slash variants are attempted transparently (``/foo`` and ``/foo/``).

**Why a query string?** The underlying path may itself be a ``{path:path}``
catch-all (``/docs/{slug:path}``) — encoding the block as a suffix segment
would be ambiguous. Query strings are CDN-friendly without ``Vary`` config.

**Handler result coercion**:

- ``Template`` / ``Page`` / ``LayoutPage`` → re-packed as ``Fragment`` with
  the requested block name and handler context.
- ``Fragment`` → returned as-is (handler already scoped to one block).
- Anything else → 400; the block-fetch URL is not meaningful for it.

No live-block registration is required at this layer — this is the raw
mechanism. Sprint 2's ``@app.live_block`` decorator adds the allowlist +
freeze-time rewriting that turns a regular block into a true live block.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from chirp._internal.invoke import invoke
from chirp.app.state import PendingRoute
from chirp.context import g
from chirp.errors import HTTPError, NotFound
from chirp.http.request import Request
from chirp.server.handler_kwargs import build_handler_kwargs
from chirp.templating.returns import Fragment, LayoutPage, Page, Template

if TYPE_CHECKING:
    from chirp.app import App

FRAGMENT_ROUTE_PREFIX = "/_frag"
"""Reserved URL prefix for block-fetch dispatching. User routes cannot start here."""

FRAGMENT_ROUTE_PATH = "/_frag/{path:path}"
"""Catch-all path registered with the router."""

FRAGMENT_QUERY_PARAM = "_b"
"""Query param carrying the block name. Short to keep URLs cache-key-friendly."""


def fragment_url(route_path: str, block_name: str) -> str:
    """Build the block-fetch URL for a ``(route_path, block_name)`` pair.

    ``route_path`` is the underlying user-route path. Leading slashes are
    normalised; trailing slashes are preserved (they affect the handler's
    view of ``request.path``). ``block_name`` is URL-safe as-is — the kida
    block-name grammar is a subset of what URLs accept.

    Usage::

        fragment_url("/docs/intro", "recent_updates")
        # "/_frag/docs/intro?_b=recent_updates"

    Also available as a template global of the same name when the app is
    compiled — use it in htmx attributes::

        <div hx-get="{{ fragment_url('/docs/intro', 'recent_updates') }}"
             hx-trigger="load">loading…</div>
    """
    path = "/" + route_path.lstrip("/")
    return f"{FRAGMENT_ROUTE_PREFIX}{path}?{FRAGMENT_QUERY_PARAM}={block_name}"


class _BadFragmentRequest(HTTPError):  # noqa: N818
    """400 — the fragment URL is well-formed but can't be dispatched."""

    def __init__(self, detail: str) -> None:
        super().__init__(status=400, detail=detail)


def _normalize_target_path(encoded: str) -> str:
    """Build the underlying path from the catch-all segment.

    The catch-all strips the leading ``/_frag/``. We put back a single leading
    slash. Trailing-slash handling is left to the caller (we try both).
    """
    return "/" + encoded.lstrip("/")


def _coerce_to_fragment(result: Any, block_name: str) -> Fragment:
    """Convert a handler's return value into a ``Fragment`` for *block_name*.

    Raises ``_BadFragmentRequest`` for streaming / mutation / redirect results
    — those have no single block to extract.
    """
    if isinstance(result, Fragment):
        return result
    if isinstance(result, (Template, Page, LayoutPage)):
        return Fragment(result.template_name, block_name, **result.context)
    raise _BadFragmentRequest(
        f"cannot extract block from {type(result).__name__}; "
        "block-fetch requires Template/Page/LayoutPage/Fragment"
    )


async def _dispatch_fragment(app: App, request: Request) -> Fragment:
    """Match the underlying route, invoke its handler, re-pack as a Fragment."""
    runtime = app._runtime_state
    router = runtime.router
    if router is None:
        raise _BadFragmentRequest("router not compiled")

    encoded = request.path_params.get("path", "")
    block = request.query.get(FRAGMENT_QUERY_PARAM)
    if not block:
        raise _BadFragmentRequest(f"missing {FRAGMENT_QUERY_PARAM!r} query param")

    target_path = _normalize_target_path(encoded)
    try:
        match = router.match("GET", target_path)
    except NotFound:
        # Many routes register with a trailing slash; retry once.
        if not target_path.endswith("/"):
            match = router.match("GET", target_path + "/")
            target_path = target_path + "/"
        else:
            raise

    # Guard: don't recurse into ourselves.
    if match.route.path == FRAGMENT_ROUTE_PATH:
        raise _BadFragmentRequest("cannot fetch fragment of the fragment dispatcher")

    # Guard: `referenced=True` flags framework-internal/SSE routes. SSE and
    # streaming responses have no single block to extract, and exposing
    # internal routes through this endpoint is not the point of the feature.
    if match.route.referenced:
        raise NotFound(f"route {target_path!r} is not block-addressable")

    # Make the underlying handler see its native path + path_params. We keep
    # the same query, headers, cookies, and body callables so handlers that
    # read query parameters (including `_b`) still work; `_b` is just noise
    # to them.
    target_request = replace(
        request,
        method="GET",
        path=target_path,
        path_params=match.path_params,
    )

    # Stash the block on `g` so handler code / middleware can introspect
    # "is this a block-fetch?" without plumbing a new arg.
    g.chirp_fragment_block = block

    plan = match.route.invoke_plan
    kwargs = build_handler_kwargs(
        match.route.handler,
        target_request,
        match.path_params,
        app._mutable_state.providers,
        body_data=None,
        invoke_plan=plan,
    )

    invoke_kw: dict[str, Any] = {}
    if plan is not None:
        invoke_kw["is_async"] = plan.is_async
        invoke_kw["inline_sync"] = plan.inline_sync

    result = await invoke(match.route.handler, **invoke_kw, **kwargs)
    return _coerce_to_fragment(result, block)


def make_fragment_dispatch_pending_route(app: App) -> PendingRoute:
    """Return a ``PendingRoute`` that dispatches ``/_frag{path}?_b=block``.

    The closure captures *app* so the handler can reach the compiled router
    and provider registry at request time.
    """

    async def _handler(request: Request) -> Fragment:
        return await _dispatch_fragment(app, request)

    return PendingRoute(
        FRAGMENT_ROUTE_PATH,
        _handler,
        ["GET"],
        name="chirp_fragment_dispatch",
        referenced=True,
    )
