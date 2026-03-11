"""Tests for chirp._internal.invoke_plan — compiled handler dispatch metadata."""

from dataclasses import dataclass

from chirp._internal.invoke_plan import ParamSpec, compile_invoke_plan
from chirp.http.request import Request


def _no_params() -> str:
    return "ok"


def _with_request(request: Request) -> str:
    return request.path


def _with_path_param(id: int) -> str:
    return str(id)


def _with_provider_and_path(msg: str) -> str:
    return msg


async def _async_handler() -> str:
    return "async"


@dataclass(frozen=True, slots=True)
class SearchParams:
    q: str = ""


def _with_extract(params: SearchParams) -> str:
    return params.q


def test_compile_empty_handler() -> None:
    plan = compile_invoke_plan(_no_params)
    assert plan.params == ()
    assert plan.has_extract_param is False


def test_compile_request_param() -> None:
    plan = compile_invoke_plan(_with_request)
    assert plan.params == (ParamSpec("request", "request"),)
    assert plan.has_extract_param is False


def test_compile_path_param() -> None:
    plan = compile_invoke_plan(_with_path_param, path_param_names=frozenset({"id"}))
    assert plan.params == (ParamSpec("id", "path", int),)
    assert plan.has_extract_param is False


def test_compile_path_takes_priority_over_provider() -> None:
    """Path params shadow providers when both match (e.g. msg: str with provide(str))."""
    plan = compile_invoke_plan(
        _with_provider_and_path,
        providers={str: lambda: "from-provider"},
        path_param_names=frozenset({"msg"}),
    )
    assert plan.params == (ParamSpec("msg", "path", str),)


def test_compile_provider_when_not_path_param() -> None:
    plan = compile_invoke_plan(
        _with_provider_and_path,
        providers={str: lambda: "from-provider"},
        path_param_names=frozenset(),  # msg not in path
    )
    assert plan.params == (ParamSpec("msg", "provider", str),)


def test_compile_extractable_dataclass_param() -> None:
    plan = compile_invoke_plan(_with_extract)
    assert plan.params == (ParamSpec("params", "extract", SearchParams),)
    assert plan.has_extract_param is True


def test_is_async_false_for_sync_handler() -> None:
    plan = compile_invoke_plan(_no_params)
    assert plan.is_async is False


def test_is_async_true_for_async_handler() -> None:
    plan = compile_invoke_plan(_async_handler)
    assert plan.is_async is True


def test_inline_sync_set_when_inline_and_sync() -> None:
    plan = compile_invoke_plan(_no_params, inline=True)
    assert plan.inline_sync is True
    assert plan.is_async is False


def test_inline_sync_false_for_async_handler() -> None:
    """inline=True on an async handler does not set inline_sync."""
    plan = compile_invoke_plan(_async_handler, inline=True)
    assert plan.inline_sync is False
    assert plan.is_async is True


def test_inline_sync_default_false() -> None:
    plan = compile_invoke_plan(_no_params)
    assert plan.inline_sync is False
