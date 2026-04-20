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


def _make_boosted_request(
    *,
    path: str,
    hx_target: bytes | None,
    current_url: bytes = b"http://127.0.0.1:8000/",
) -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    headers: list[tuple[bytes, bytes]] = [
        (b"hx-request", b"true"),
        (b"hx-boosted", b"true"),
        (b"hx-current-url", current_url),
    ]
    if hx_target is not None:
        headers.append((b"hx-target", hx_target))
    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
        },
        _receive,
    )


@pytest.mark.asyncio
async def test_boosted_get_redirects_when_shell_configured_but_registries_missing() -> None:
    """Sprint 2.1: inconsistent-state safe redirect.

    swap_scope_map is populated (app uses shell) but fragment_target_registry
    is None. Framework cannot guarantee a correct swap → redirect.
    """
    router = Router()
    router.add(Route("/other", lambda: "other", frozenset({"GET"})))
    router.compile()

    handler = create_request_handler(
        router=router,
        middleware=(),
        tool_registry=None,
        mcp_path="/mcp",
        debug=False,
        providers=None,
        kida_env=None,
        fragment_target_registry=None,
        route_layout_chains=None,
        swap_scope_map={"site": "site-content"},
    )

    request = _make_boosted_request(path="/other", hx_target=b"site-content")
    response = await handler(request)

    assert isinstance(response, Response)
    assert_hx_redirect(response, "/other")
    assert response.status != 500


@pytest.mark.asyncio
async def test_boosted_get_passes_through_when_no_app_shell() -> None:
    """Regression guard: apps without app-shell must not be redirected.

    Empty swap_scope_map means the app does not use the shell system.
    Boosted GETs render via normal dispatch, not the cross-shell path.
    """
    router = Router()
    router.add(Route("/other", lambda: "other", frozenset({"GET"})))
    router.compile()

    handler = create_request_handler(
        router=router,
        middleware=(),
        tool_registry=None,
        mcp_path="/mcp",
        debug=False,
        providers=None,
        kida_env=None,
        fragment_target_registry=None,
        route_layout_chains=None,
        swap_scope_map={},
    )

    request = _make_boosted_request(path="/other", hx_target=b"main")
    response = await handler(request)

    assert isinstance(response, Response)
    assert response.text == "other"
    assert "HX-Redirect" not in {k for k, _ in response.headers}


@pytest.mark.asyncio
async def test_boosted_get_redirects_when_no_shared_navigation_ancestor() -> None:
    """Sprint 2.2: true cross-shell → redirect.

    Two routes with separate layout chains that share no navigation
    ancestor. resolve_navigation_swap returns None; we must still
    redirect rather than render a fragment into a DOM target that
    doesn't exist in the current shell.
    """
    router = Router()
    router.add(Route("/shell-a", lambda: "in-shell-a", frozenset({"GET"})))
    router.add(Route("/shell-b", lambda: "in-shell-b", frozenset({"GET"})))
    router.compile()

    registry = FragmentTargetRegistry()
    registry.register("shell-a-content", fragment_block="content", scope_name="shell_a")
    registry.register("shell-b-content", fragment_block="content", scope_name="shell_b")
    registry.freeze()

    route_layout_chains = {
        "/shell-a": LayoutChain(
            (
                LayoutInfo(
                    "pages/shell_a/_layout.html",
                    "body",
                    0,
                    domain_name="shell_a",
                    swap_scope_name="shell_a",
                    outlet_target_id="shell-a-content",
                ),
            )
        ),
        "/shell-b": LayoutChain(
            (
                LayoutInfo(
                    "pages/shell_b/_layout.html",
                    "body",
                    0,
                    domain_name="shell_b",
                    swap_scope_name="shell_b",
                    outlet_target_id="shell-b-content",
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
        fragment_target_registry=registry,
        route_layout_chains=route_layout_chains,
        swap_scope_map={"shell_a": "shell-a-content", "shell_b": "shell-b-content"},
    )

    request = _make_boosted_request(
        path="/shell-b",
        hx_target=b"shell-a-content",
        current_url=b"http://127.0.0.1:8000/shell-a",
    )
    response = await handler(request)

    assert isinstance(response, Response)
    assert_hx_redirect(response, "/shell-b")
    assert response.status != 500


@pytest.mark.asyncio
async def test_boosted_get_junk_target_does_not_500() -> None:
    """Robustness: a malformed HX-Target header must never produce a 500.

    Client sends an HTML-doctype-like value in HX-Target (e.g. pasted
    markup, adversarial input). The framework should either redirect
    or pass through — but never crash.
    """
    router = Router()
    router.add(Route("/", lambda: "home", frozenset({"GET"})))
    router.add(Route("/showcase", lambda: "showcase", frozenset({"GET"})))
    router.compile()

    registry = FragmentTargetRegistry()
    registry.register("site-content", fragment_block="content", scope_name="site")
    registry.freeze()

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
        fragment_target_registry=registry,
        route_layout_chains=route_layout_chains,
        swap_scope_map={"site": "site-content"},
    )

    request = _make_boosted_request(path="/showcase", hx_target=b"<!DOCTYPE-junk")
    response = await handler(request)

    assert isinstance(response, Response)
    assert response.status != 500
