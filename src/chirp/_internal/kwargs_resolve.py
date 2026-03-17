"""Shared kwargs-building logic for page handlers and route handlers."""

import inspect
from collections.abc import Callable
from typing import Any

from chirp.extraction import extract_dataclass, is_extractable_dataclass


def build_base_kwargs(
    sig: inspect.Signature,
    request: object,
    path_params: dict[str, str],
    body_data: dict[str, Any] | None,
    *,
    cascade_ctx: dict[str, Any] | None = None,
    providers: dict[type, Callable[..., Any]] | None = None,
    invoke_provider: Callable[[Callable[..., Any], object, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Build kwargs from signature using request, path params, context, providers, body.

    Resolution order: request → path_params → cascade_ctx → providers → dataclass extract.
    When invoke_provider is set, providers are called via invoke_provider(factory, request, ctx).
    Otherwise providers are called as factory().
    """
    from chirp.http.request import Request as RequestType

    kwargs: dict[str, Any] = {}
    ctx = cascade_ctx or {}

    for name, param in sig.parameters.items():
        if name == "request" or param.annotation is RequestType:
            kwargs[name] = request
        elif name in path_params:
            value = path_params[name]
            if param.annotation is not inspect.Parameter.empty:
                try:
                    kwargs[name] = param.annotation(value)
                except ValueError, TypeError:
                    kwargs[name] = value
            else:
                kwargs[name] = value
        elif name in ctx:
            kwargs[name] = ctx[name]
        elif (
            providers is not None
            and param.annotation is not inspect.Parameter.empty
            and param.annotation in providers
        ):
            factory = providers[param.annotation]
            if invoke_provider is not None:
                kwargs[name] = invoke_provider(factory, request, ctx)
            else:
                kwargs[name] = factory()
        elif param.annotation is not inspect.Parameter.empty and is_extractable_dataclass(
            param.annotation
        ):
            method = getattr(request, "method", "GET")
            if method in ("GET", "HEAD"):
                query = getattr(request, "query", {})
                kwargs[name] = extract_dataclass(param.annotation, query)
            elif body_data is not None:
                kwargs[name] = extract_dataclass(param.annotation, body_data)

    return kwargs
