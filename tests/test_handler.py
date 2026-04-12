"""Tests for chirp.server.handler — middleware chain compilation."""

import pytest

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.handler import compile_middleware_chain, create_request_handler
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.testing import assert_hx_redirect


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


@pytest.mark.asyncio
async def test_create_request_handler_allows_shared_ancestor_boosted_get() -> None:
    router = Router()
    router.add(Route("/", lambda: "home", frozenset({"GET"})))
    router.add(Route("/showcase", lambda: "showcase", frozenset({"GET"})))
    router.compile()

    fragment_target_registry = FragmentTargetRegistry()
    fragment_target_registry.register("site-content", fragment_block="content", scope_name="site")
    fragment_target_registry.register("main", fragment_block="page_root", scope_name="section")
    fragment_target_registry.freeze()

    route_layout_chains = {
        "/": LayoutChain(
            (
                LayoutInfo(
                    "pages/_layout.html",
                    "body",
                    0,
                    domain_name="site",
                    swap_scope_name="site",
                    outlet_target_id="site-content",
                ),
            )
        ),
        "/showcase": LayoutChain(
            (
                LayoutInfo(
                    "pages/_layout.html",
                    "body",
                    0,
                    domain_name="site",
                    swap_scope_name="site",
                    outlet_target_id="site-content",
                ),
                LayoutInfo(
                    "pages/showcase/_layout.html",
                    "main",
                    1,
                    domain_name="showcase",
                    shell_name="showcase-shell",
                    swap_scope_name="section",
                ),
            )
        ),
    }

    handler = create_request_handler(
        router=router,
        middleware=(),
        tool_registry=None,
        mcp_path="/mcp",
        debug=False,
        providers=None,
        kida_env=None,
        fragment_target_registry=fragment_target_registry,
        route_layout_chains=route_layout_chains,
        swap_scope_map={"site": "site-content", "section": "main"},
    )

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/showcase",
            "headers": [
                (b"hx-request", b"true"),
                (b"hx-boosted", b"true"),
                (b"hx-target", b"site-content"),
                (b"hx-current-url", b"http://127.0.0.1:8000/"),
            ],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
        },
        _receive,
    )

    response = await handler(request)

    assert isinstance(response, Response)
    assert response.text == "showcase"


@pytest.mark.asyncio
async def test_create_request_handler_redirects_boosted_get_with_wrong_target() -> None:
    router = Router()
    router.add(Route("/", lambda: "home", frozenset({"GET"})))
    router.add(Route("/showcase", lambda: "showcase", frozenset({"GET"})))
    router.compile()

    fragment_target_registry = FragmentTargetRegistry()
    fragment_target_registry.register("site-content", fragment_block="content", scope_name="site")
    fragment_target_registry.register("main", fragment_block="page_root", scope_name="section")
    fragment_target_registry.freeze()

    route_layout_chains = {
        "/": LayoutChain(
            (
                LayoutInfo(
                    "pages/_layout.html",
                    "body",
                    0,
                    domain_name="site",
                    swap_scope_name="site",
                    outlet_target_id="site-content",
                ),
            )
        ),
        "/showcase": LayoutChain(
            (
                LayoutInfo(
                    "pages/_layout.html",
                    "body",
                    0,
                    domain_name="site",
                    swap_scope_name="site",
                    outlet_target_id="site-content",
                ),
                LayoutInfo(
                    "pages/showcase/_layout.html",
                    "main",
                    1,
                    domain_name="showcase",
                    shell_name="showcase-shell",
                    swap_scope_name="section",
                ),
            )
        ),
    }

    handler = create_request_handler(
        router=router,
        middleware=(),
        tool_registry=None,
        mcp_path="/mcp",
        debug=False,
        providers=None,
        kida_env=None,
        fragment_target_registry=fragment_target_registry,
        route_layout_chains=route_layout_chains,
        swap_scope_map={"site": "site-content", "section": "main"},
    )

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/showcase",
            "headers": [
                (b"hx-request", b"true"),
                (b"hx-boosted", b"true"),
                (b"hx-target", b"main"),
                (b"hx-current-url", b"http://127.0.0.1:8000/"),
            ],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
        },
        _receive,
    )

    response = await handler(request)

    assert isinstance(response, Response)
    assert_hx_redirect(response, "/showcase")
    assert response.text == ""
