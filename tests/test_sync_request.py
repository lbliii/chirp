"""Tests for chirp.http.sync_request — lightweight request for fused sync path."""

from pounce.sync_protocol import RawRequest

from chirp.http.sync_request import SyncRequest


def _raw(
    method: bytes = b"GET", path: bytes = b"/", query: bytes = b"", headers: tuple = ()
) -> RawRequest:
    return RawRequest(
        method=method,
        path=path + (b"?" + query if query else b""),
        query_string=query,
        headers=headers,
        body=b"",
        client=("127.0.0.1", 12345),
        server=("127.0.0.1", 8000),
        http_version=b"1.1",
    )


def test_sync_request_query_lazy() -> None:
    raw = _raw(query=b"foo=bar&baz=qux")
    req = SyncRequest("GET", "/", _raw=raw)
    assert req.query.get("foo") == "bar"
    assert req.query.get("baz") == "qux"
    assert req.query.get("missing") is None


def test_sync_request_query_empty() -> None:
    raw = _raw()
    req = SyncRequest("GET", "/", _raw=raw)
    assert req.query.get("x") is None
    assert len(req.query) == 0


def test_sync_request_cookies_lazy() -> None:
    raw = _raw(headers=((b"cookie", b"session=abc123; theme=dark"),))
    req = SyncRequest("GET", "/", _raw=raw)
    assert req.cookies["session"] == "abc123"
    assert req.cookies["theme"] == "dark"


def test_sync_request_cookies_empty() -> None:
    raw = _raw()
    req = SyncRequest("GET", "/", _raw=raw)
    assert req.cookies == {}


def test_sync_request_headers_lazy() -> None:
    raw = _raw(headers=((b"content-type", b"application/json"), (b"x-custom", b"value")))
    req = SyncRequest("GET", "/", _raw=raw)
    assert req.headers.get("content-type") == "application/json"
    assert req.headers.get("x-custom") == "value"


def test_sync_request_path_params() -> None:
    raw = _raw()
    req = SyncRequest("GET", "/users/42", _raw=raw, path_params={"id": "42"})
    assert req.path_params == {"id": "42"}
    assert req.path == "/users/42"
    assert req.method == "GET"
