"""Fused sync handler — bypasses ASGI for simple request-response paths."""

from __future__ import annotations

import json
from typing import Any

from chirp._internal.invoke_plan import InvokePlan
from chirp.errors import MethodNotAllowed, NotFound
from chirp.http.sync_request import SyncRequest
from chirp.routing.router import Router
from pounce.sync_protocol import RawRequest, RawResponse


def handle_sync(
    raw: RawRequest,
    router: Router,
    middleware: tuple[Any, ...],
    providers: dict[type, Any] | None,
) -> RawResponse | None:
    """Handle a sync request via the fused path.

    Returns RawResponse for sync handling, or None to fall through to ASGI.
    Requires no middleware (middleware bypasses sync path).
    """

    # Middleware must be empty for sync path — we bypass it
    if middleware:
        return None

    method = raw.method.decode("ascii")
    path = raw.path.split(b"?", 1)[0].decode("ascii")

    try:
        match = router.match(method, path)
    except NotFound:
        return None
    except MethodNotAllowed:
        return None

    plan = getattr(match.route, "invoke_plan", None)
    if plan is None or not getattr(plan, "sync_eligible", False):
        return None

    # Build SyncRequest only if handler needs it
    needs_request = any(p.source == "request" for p in plan.params)
    request: SyncRequest | None = None
    if needs_request:
        request = SyncRequest(method=method, path=path, _raw=raw, path_params=match.path_params)

    kwargs = _build_sync_kwargs(plan, request, match.path_params, providers)

    try:
        result = match.route.handler(**kwargs)
    except Exception:
        return None

    # Fast negotiate for common types — use pre-encoded content-type when available
    content_type = getattr(plan, "response_content_type_bytes", None)
    if isinstance(result, (dict, list)):
        body = json.dumps(result, default=str, separators=(",", ":")).encode()
        ct = content_type if content_type else b"application/json"
        return RawResponse(200, ((b"content-type", ct),), body)
    if isinstance(result, str):
        body = result.encode()
        ct = content_type if content_type else b"text/html; charset=utf-8"
        return RawResponse(200, ((b"content-type", ct),), body)
    if isinstance(result, bytes):
        ct = content_type if content_type else b"application/octet-stream"
        return RawResponse(200, ((b"content-type", ct),), result)

    return None


def _build_sync_kwargs(
    plan: InvokePlan,
    request: SyncRequest | None,
    path_params: dict[str, str],
    providers: dict[type, Any] | None,
) -> dict[str, Any]:
    """Build kwargs for sync handler from InvokePlan."""
    kwargs: dict[str, Any] = {}
    for spec in plan.params:
        if spec.source == "request" and request is not None:
            kwargs[spec.name] = request
        elif spec.source == "path" and spec.name in path_params:
            value = path_params[spec.name]
            if spec.annotation is not None:
                try:
                    kwargs[spec.name] = spec.annotation(value)
                except (ValueError, TypeError):
                    kwargs[spec.name] = value
            else:
                kwargs[spec.name] = value
        elif spec.source == "provider" and spec.annotation and providers:
            provider = providers.get(spec.annotation)
            if provider is not None:
                kwargs[spec.name] = provider()
    return kwargs
