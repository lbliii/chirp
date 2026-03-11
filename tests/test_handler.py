"""Tests for chirp.server.handler — middleware chain compilation."""

import pytest

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.handler import compile_middleware_chain, create_request_handler


@pytest.fixture
def mock_request() -> Request:
    from chirp.http.headers import Headers
    from chirp.http.request import _LazyCookies, _LazyQueryParams

    return Request(
        method="GET",
        path="/",
        headers=Headers(()),
        query=_LazyQueryParams(b""),
        path_params={},
        http_version="1.1",
        server=("127.0.0.1", 8000),
        client=("127.0.0.1", 12345),
        cookies=_LazyCookies(""),
        request_id="test-id",
        _receive=lambda: {"body": b"", "more_body": False},
    )


@pytest.mark.asyncio
async def test_compile_middleware_chain_empty_passes_through(mock_request: Request) -> None:
    async def dispatch(req: Request) -> Response:
        return Response(body=req.path.encode(), content_type="text/plain")

    chain = compile_middleware_chain((), dispatch)
    result = await chain(mock_request)
    assert isinstance(result, Response)
    assert result.body == b"/"


@pytest.mark.asyncio
async def test_compile_middleware_chain_single_middleware(mock_request: Request) -> None:
    async def dispatch(req: Request) -> Response:
        return Response(body=b"inner", content_type="text/plain")

    async def add_header(req: Request, next) -> Response:
        resp = await next(req)
        return resp.with_header("X-Custom", "added")

    chain = compile_middleware_chain((add_header,), dispatch)
    result = await chain(mock_request)
    assert isinstance(result, Response)
    assert result.body == b"inner"
    header_names = {h[0].lower() for h in result.headers}
    assert "x-custom" in header_names
    x_custom = next(v for n, v in result.headers if n.lower() == "x-custom")
    assert x_custom == "added"


@pytest.mark.asyncio
async def test_create_request_handler_returns_callable(mock_request: Request) -> None:
    router = Router()
    router.add(Route("/", lambda: "ok", frozenset({"GET"})))
    router.compile()

    handler = create_request_handler(
        router=router,
        middleware=(),
        tool_registry=None,
        mcp_path="/mcp",
        debug=False,
        providers=None,
        kida_env=None,
    )
    assert callable(handler)
    result = await handler(mock_request)
    assert isinstance(result, Response)
    body = result.body if isinstance(result.body, bytes) else result.body.encode()
    assert b"ok" in body
