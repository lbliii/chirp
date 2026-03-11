"""Compiled handler invocation plan — moves per-request reflection out of hot path.

At freeze time we inspect each route handler once and produce an InvokePlan
that describes how to build kwargs. The handler uses this plan instead of
calling inspect.signature() on every request.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, get_origin

from chirp.http.request import Request


type ParamSource = Literal["request", "path", "provider", "extract"]


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """Spec for one handler parameter — where to get its value."""

    name: str
    source: ParamSource
    annotation: type[Any] | None = None  # for path conversion, extract type, provider type


@dataclass(frozen=True, slots=True)
class InvokePlan:
    """Precomputed handler invocation plan.

    Built once at freeze time from handler signature and providers.
    Used by handler to build kwargs without inspect.signature per request.
    """

    params: tuple[ParamSpec, ...]
    has_extract_param: bool  # True if any extract param (body needed for non-GET)
    is_async: bool = False
    inline_sync: bool = False
    sync_eligible: bool = False  # True if: not async, no streaming, no middleware-dependent
    response_content_type_bytes: bytes | None = None  # e.g. b"application/json"


def compile_invoke_plan(
    handler: Callable[..., Any],
    providers: dict[type, Callable[..., Any]] | None = None,
    *,
    path_param_names: frozenset[str] | None = None,
    inline: bool = False,
) -> InvokePlan:
    """Inspect handler signature once and produce an InvokePlan.

    Path params take priority over providers when a param name appears in both.
    """
    from chirp.extraction import is_extractable_dataclass

    path_params = path_param_names or frozenset()
    sig = inspect.signature(handler, eval_str=True)
    params: list[ParamSpec] = []
    has_extract_param = False

    for name, param in sig.parameters.items():
        annotation = param.annotation if param.annotation is not inspect.Parameter.empty else None

        if name == "request" or annotation is Request:
            params.append(ParamSpec(name, "request"))
        elif name in path_params:
            params.append(ParamSpec(name, "path", annotation))
        elif annotation is not None and providers and annotation in providers:
            params.append(ParamSpec(name, "provider", annotation))
        elif annotation is not None and is_extractable_dataclass(annotation):
            params.append(ParamSpec(name, "extract", annotation))
            has_extract_param = True
        else:
            params.append(ParamSpec(name, "path", annotation))

    handler_is_async = inspect.iscoroutinefunction(handler)
    # Exclude extract params: POST body parsing would need async in full Request
    sync_eligible = not handler_is_async and not has_extract_param

    # Infer response content-type from return annotation for fused path
    response_content_type_bytes: bytes | None = None
    ret_ann = sig.return_annotation
    if ret_ann is not inspect.Signature.empty:
        origin = get_origin(ret_ann) or ret_ann
        if origin is dict or origin is list:
            response_content_type_bytes = b"application/json"
        elif ret_ann is str:
            response_content_type_bytes = b"text/html; charset=utf-8"
        elif ret_ann is bytes:
            response_content_type_bytes = b"application/octet-stream"

    return InvokePlan(
        params=tuple(params),
        has_extract_param=has_extract_param,
        is_async=handler_is_async,
        inline_sync=inline and not handler_is_async,
        sync_eligible=sync_eligible,
        response_content_type_bytes=response_content_type_bytes,
    )
