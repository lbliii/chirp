"""Handler kwargs building — path params, providers, body extraction."""

from collections.abc import Callable
from typing import Any

from chirp._internal.invoke_plan import InvokePlan
from chirp.http.request import Request


def build_handler_kwargs(
    handler: Callable[..., Any],
    request: Request,
    path_params: dict[str, str],
    providers: dict[type, Callable[..., Any]] | None = None,
    *,
    body_data: dict[str, Any] | None = None,
    invoke_plan: InvokePlan | None = None,
) -> dict[str, Any]:
    """Build kwargs from request + path params using compiled plan or inspection.

    When invoke_plan is present, uses the precomputed plan (no inspect per request).
    Falls back to _build_handler_kwargs_inspect for routes without a plan.
    """
    if invoke_plan is not None:
        return _build_handler_kwargs_from_plan(
            request, path_params, providers, body_data, invoke_plan
        )
    return _build_handler_kwargs_inspect(handler, request, path_params, providers, body_data)


def _build_handler_kwargs_from_plan(
    request: Request,
    path_params: dict[str, str],
    providers: dict[type, Callable[..., Any]] | None,
    body_data: dict[str, Any] | None,
    plan: InvokePlan,
) -> dict[str, Any]:
    """Build kwargs using compiled InvokePlan — allocation-light fast path."""

    from chirp.extraction import extract_dataclass

    kwargs: dict[str, Any] = {}
    for spec in plan.params:
        if spec.source == "request":
            kwargs[spec.name] = request
        elif spec.source == "path" and spec.name in path_params:
            value = path_params[spec.name]
            if spec.annotation is not None:
                try:
                    kwargs[spec.name] = spec.annotation(value)
                except ValueError, TypeError:
                    kwargs[spec.name] = value
            else:
                kwargs[spec.name] = value
        elif spec.source == "provider" and spec.annotation and providers:
            provider = providers.get(spec.annotation)
            if provider is not None:
                kwargs[spec.name] = provider()
        elif spec.source == "extract" and spec.annotation is not None:
            if request.method in ("GET", "HEAD"):
                kwargs[spec.name] = extract_dataclass(spec.annotation, request.query)
            elif body_data is not None:
                kwargs[spec.name] = extract_dataclass(spec.annotation, body_data)
    return kwargs


def _build_handler_kwargs_inspect(
    handler: Callable[..., Any],
    request: Request,
    path_params: dict[str, str],
    providers: dict[type, Callable[..., Any]] | None,
    body_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fallback: inspect handler signature and build kwargs (used when no plan)."""
    import inspect

    from chirp._internal.kwargs_resolve import build_base_kwargs

    sig = inspect.signature(handler, eval_str=True)
    return build_base_kwargs(
        sig,
        request,
        path_params,
        body_data,
        providers=providers,
    )
