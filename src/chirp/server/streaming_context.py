"""Capture and re-establish request-scoped state for deferred stream rendering.

``Suspense``, ``Stream``, and other ``StreamingResponse`` generators often run
after middleware ``finally`` blocks reset ContextVars. CSP nonce already uses
``StreamingResponse.csp_nonce``; auth and CSRF follow the same pattern.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from chirp.http.response import StreamingResponse


def capture_streaming_render_context() -> tuple[Any, str | None, str | None]:
    """Snapshot auth user and CSRF token while middleware ContextVars are live."""
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

    return auth_user, csrf_token, csrf_field_name


def attach_streaming_render_context(response: StreamingResponse) -> StreamingResponse:
    """Stamp live auth/CSRF snapshots onto a streaming response when unset."""
    auth_user, csrf_token, csrf_field_name = capture_streaming_render_context()
    updates: dict[str, Any] = {}
    if auth_user is not None and response.auth_user is None:
        updates["auth_user"] = auth_user
    if csrf_token is not None and response.csrf_token is None:
        updates["csrf_token"] = csrf_token
    if csrf_field_name is not None and response.csrf_field_name is None:
        updates["csrf_field_name"] = csrf_field_name
    if not updates:
        return response
    return replace(response, **updates)
