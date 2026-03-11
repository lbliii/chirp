"""Tests for chirp.server.sync_handler — fused sync path."""

from pounce.sync_protocol import RawRequest, RawResponse

from chirp._internal.invoke_plan import compile_invoke_plan
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.sync_handler import handle_sync


def _json_handler() -> dict:
    return {"message": "hello", "count": 42}


def _html_handler() -> str:
    return "<html>ok</html>"


def _bytes_handler() -> bytes:
    return b"binary"


def _with_request(request) -> dict:
    return {"path": request.path}


def _route(path: str, handler, plan=None) -> Route:
    if plan is None:
        plan = compile_invoke_plan(handler)
    return Route(path=path, handler=handler, methods=frozenset({"GET"}), invoke_plan=plan)


def _raw(method: bytes = b"GET", path: bytes = b"/", query: bytes = b"") -> RawRequest:
    return RawRequest(
        method=method,
        path=path + (b"?" + query if query else b""),
        query_string=query,
        headers=(),
        body=b"",
        client=("127.0.0.1", 12345),
        server=("127.0.0.1", 8000),
        http_version=b"1.1",
    )


def test_handle_sync_returns_none_with_middleware() -> None:
    router = Router()
    router.add(_route("/", _json_handler))
    router.compile()
    raw = _raw(path=b"/")
    result = handle_sync(raw, router, middleware=(lambda r, n: n(r),), providers=None)
    assert result is None


def test_handle_sync_json_response() -> None:
    router = Router()
    router.add(_route("/", _json_handler))
    router.compile()
    raw = _raw(path=b"/")
    result = handle_sync(raw, router, middleware=(), providers=None)
    assert isinstance(result, RawResponse)
    assert result.status == 200
    assert b"application/json" in result.headers[0][1]
    assert result.body == b'{"message":"hello","count":42}'


def test_handle_sync_str_response() -> None:
    router = Router()
    router.add(_route("/html", _html_handler))
    router.compile()
    raw = _raw(path=b"/html")
    result = handle_sync(raw, router, middleware=(), providers=None)
    assert isinstance(result, RawResponse)
    assert result.status == 200
    assert b"text/html" in result.headers[0][1]
    assert result.body == b"<html>ok</html>"


def test_handle_sync_bytes_response() -> None:
    router = Router()
    router.add(_route("/bin", _bytes_handler))
    router.compile()
    raw = _raw(path=b"/bin")
    result = handle_sync(raw, router, middleware=(), providers=None)
    assert isinstance(result, RawResponse)
    assert result.status == 200
    assert result.body == b"binary"


def test_handle_sync_not_found_returns_none() -> None:
    router = Router()
    router.add(_route("/known", _json_handler))
    router.compile()
    raw = _raw(path=b"/unknown")
    result = handle_sync(raw, router, middleware=(), providers=None)
    assert result is None


def test_handle_sync_with_request_param() -> None:
    router = Router()
    router.add(_route("/with-req", _with_request))
    router.compile()
    raw = _raw(path=b"/with-req")
    result = handle_sync(raw, router, middleware=(), providers=None)
    assert isinstance(result, RawResponse)
    assert result.body == b'{"path":"/with-req"}'
