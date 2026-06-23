"""Capture and re-establish request-scoped state for deferred stream rendering.

``Suspense``, ``Stream``, ``EventStream``, and other streaming generators often
run *after* middleware ``finally`` blocks reset the request ContextVars
(``request_var``, the auth user, CSRF token, and ``g``). The handler resets
these before the streaming/SSE body is drained, so accessing them inside a
deferred render — ``get_request()``, ``get_user()`` / ``current_user()``,
``get_csrf_token()``, or ``g`` — would raise ``LookupError`` or return an
``AnonymousUser`` unless we capture them while they are still live and
re-establish them for the drain.

This module is the single capture-then-re-establish path shared by all three
streamed-render types. The carrier (:class:`_CapturedRequestContext`) is
**internal** — underscore-prefixed and not exported to the top-level public
surface.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from chirp.http.response import StreamingResponse

if TYPE_CHECKING:
    from chirp.http.request import Request


@dataclass(frozen=True, slots=True)
class _CapturedRequestContext:
    """Snapshot of request-scoped state captured while ContextVars are live.

    Carried onto :class:`~chirp.http.response.StreamingResponse` /
    :class:`~chirp.http.response.SSEResponse` so the drain (``send_streaming_response``
    for ``Suspense``/``Stream``, ``produce_events`` for ``EventStream``) can
    re-establish identical request context. Internal — not public API.

    Fields:
        auth_user: The authenticated ``User`` (or ``AnonymousUser``), or ``None``
            when ``AuthMiddleware`` was not active.
        csrf_token: The CSRF token string, or ``None``.
        csrf_field_name: The CSRF form field name, or ``None``.
        g_snapshot: A shallow copy of ``g``'s store, or ``None`` when ``g`` was
            never touched (the zero-``g`` hot path allocates nothing).
        request_context: The current :class:`~chirp.http.request.Request`, or
            ``None``.
        csp_nonce: The live CSP nonce, or ``None`` when CSP nonces are disabled.
        runtime_context: A :func:`contextvars.copy_context` snapshot taken while
            middleware and OTel spans are still live, re-attached when the SSE
            producer task starts so trace context survives the handler ``finally``.
    """

    auth_user: Any | None = None
    csrf_token: str | None = None
    csrf_field_name: str | None = None
    g_snapshot: dict[str, Any] | None = None
    request_context: Request | None = None
    csp_nonce: str | None = None
    runtime_context: contextvars.Context | None = None


def capture_streaming_render_context(
    *,
    request_context: Request | None = None,
    csp_nonce: str | None = None,
) -> _CapturedRequestContext:
    """Snapshot request/user/CSRF/g/nonce while middleware ContextVars are live.

    *request_context* and *csp_nonce* are passed in by the caller (the negotiation
    site already holds the live request and nonce); the auth user, CSRF token,
    and ``g`` are read from their ContextVars here.
    """
    auth_user = None
    csrf_token: str | None = None
    csrf_field_name: str | None = None

    try:
        from chirp.middleware.auth import get_user

        auth_user = get_user()
    except LookupError:
        pass

    try:
        from chirp.middleware.csrf import _csrf_field_name_var, get_csrf_token

        csrf_token = get_csrf_token()
        csrf_field_name = _csrf_field_name_var.get()
    except LookupError:
        pass

    # g.snapshot() reads the RAW ContextVar and returns None when the store is
    # None, so the zero-g hot path allocates nothing.
    from chirp.context import g

    g_snapshot = g.snapshot()

    from chirp._internal.invoke import take_handler_runtime_context

    runtime_context = take_handler_runtime_context()
    if runtime_context is None:
        runtime_context = contextvars.copy_context()

    return _CapturedRequestContext(
        auth_user=auth_user,
        csrf_token=csrf_token,
        csrf_field_name=csrf_field_name,
        g_snapshot=g_snapshot,
        request_context=request_context,
        csp_nonce=csp_nonce,
        runtime_context=runtime_context,
    )


def attach_streaming_render_context(response: StreamingResponse) -> StreamingResponse:
    """Stamp live request-scoped snapshots onto a streaming response when unset."""
    captured = capture_streaming_render_context()
    updates: dict[str, Any] = {}
    if captured.auth_user is not None and response.auth_user is None:
        updates["auth_user"] = captured.auth_user
    if captured.csrf_token is not None and response.csrf_token is None:
        updates["csrf_token"] = captured.csrf_token
    if captured.csrf_field_name is not None and response.csrf_field_name is None:
        updates["csrf_field_name"] = captured.csrf_field_name
    # Gate on `is not None` (not truthiness): an empty-dict snapshot must still
    # install a writable g store for the drain.
    if captured.g_snapshot is not None and response.g_snapshot is None:
        updates["g_snapshot"] = captured.g_snapshot
    if not updates:
        return response
    return replace(response, **updates)
