"""Collision, privacy, lifecycle, and stability proof for QUERY cache keys (#530)."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from chirp.cache.key import query_cache_key
from chirp.errors import PayloadTooLarge
from chirp.http.request import Request

pytestmark = pytest.mark.issue(530)

_KEY_RE = re.compile(r"^chirp:query:v1:[0-9a-f]{64}$")


def _request(
    *,
    method: str = "QUERY",
    body: bytes = b'{"term":"private-search"}',
    path: str = "/search/private-path",
    query: bytes = b"page=2&private_uri_value=hidden",
    headers: tuple[tuple[bytes, bytes], ...] = (
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-encoding", b"identity"),
        (b"accept", b"text/html"),
        (b"hx-request", b"true"),
        (b"hx-boosted", b"true"),
        (b"hx-history-restore-request", b"true"),
        (b"hx-target", b"results"),
        (b"hx-partial", b"result-card"),
        (b"x-tenant", b"public"),
        (b"x-locale", b"en"),
    ),
    max_body_size: int | None = 16 * 1024 * 1024,
    receive_counter: list[int] | None = None,
) -> Request:
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if receive_counter is not None:
            receive_counter[0] += 1
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query,
        "root_path": "",
        "headers": list(headers),
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
    }
    return Request.from_asgi(
        scope,
        receive,
        max_request_body_size=max_body_size,
    )


def _replace_header(
    headers: tuple[tuple[bytes, bytes], ...],
    name: bytes,
    value: bytes | None,
) -> tuple[tuple[bytes, bytes], ...]:
    output = [(key, item) for key, item in headers if key.lower() != name.lower()]
    if value is not None:
        output.append((name, value))
    return tuple(output)


_BASE_HEADERS = _request().headers.raw


@pytest.mark.parametrize(
    ("dimension", "request_change", "vary_change"),
    [
        ("body", {"body": b'{"term":"other"}'}, None),
        ("path", {"path": "/search/other"}, None),
        ("URI query", {"query": b"page=3&private_uri_value=hidden"}, None),
        (
            "content type parameter",
            {
                "headers": _replace_header(
                    _BASE_HEADERS,
                    b"content-type",
                    b"application/json; charset=us-ascii",
                )
            },
            None,
        ),
        (
            "content encoding",
            {"headers": _replace_header(_BASE_HEADERS, b"content-encoding", b"gzip")},
            None,
        ),
        (
            "Accept",
            {"headers": _replace_header(_BASE_HEADERS, b"accept", b"text/plain")},
            None,
        ),
        (
            "htmx shape",
            {"headers": _replace_header(_BASE_HEADERS, b"hx-request", None)},
            None,
        ),
        (
            "boosted shape",
            {"headers": _replace_header(_BASE_HEADERS, b"hx-boosted", None)},
            None,
        ),
        (
            "history shape",
            {
                "headers": _replace_header(
                    _BASE_HEADERS,
                    b"hx-history-restore-request",
                    None,
                )
            },
            None,
        ),
        (
            "target id",
            {"headers": _replace_header(_BASE_HEADERS, b"hx-target", b"sidebar")},
            None,
        ),
        (
            "partial name",
            {"headers": _replace_header(_BASE_HEADERS, b"hx-partial", b"summary-card")},
            None,
        ),
        (
            "configured vary value",
            {"headers": _replace_header(_BASE_HEADERS, b"x-tenant", b"other")},
            None,
        ),
        ("configured vary name", {}, ("x-locale",)),
    ],
)
async def test_query_cache_key_varies_each_input_dimension(
    dimension: str,
    request_change: dict[str, object],
    vary_change: tuple[str, ...] | None,
) -> None:
    base = await query_cache_key(_request(), vary_headers=("x-tenant",))
    changed = await query_cache_key(
        _request(**request_change),
        vary_headers=vary_change or ("x-tenant",),
    )
    assert base != changed, f"QUERY cache key collided when varying {dimension}"


async def test_query_cache_key_is_stable_opaque_and_body_reusable() -> None:
    body = b'{"token":"do-not-log-this"}'
    receive_calls = [0]
    request = _request(body=body, receive_counter=receive_calls)

    first = await query_cache_key(request, vary_headers=("X-Tenant", "x-tenant"))
    second = await query_cache_key(request, vary_headers=("x-tenant",))

    assert first == second
    assert _KEY_RE.fullmatch(first)
    assert "do-not-log-this" not in first
    assert "private-path" not in first
    assert "private_uri_value" not in first
    assert await request.body() == body
    assert receive_calls == [1]


async def test_equivalent_header_and_vary_configuration_order_is_stable() -> None:
    original = await query_cache_key(
        _request(headers=_BASE_HEADERS),
        vary_headers=("x-tenant", "X-Locale"),
    )
    reordered = await query_cache_key(
        _request(headers=tuple(reversed(_BASE_HEADERS))),
        vary_headers=("x-locale", "X-Tenant", "x-locale"),
    )

    assert original == reordered


async def test_query_cache_key_preserves_exact_header_values_and_order() -> None:
    headers = (
        *_replace_header(_BASE_HEADERS, b"accept", None),
        (b"accept", b"text/html"),
        (b"accept", b"text/plain"),
    )
    reversed_headers = (
        *_replace_header(_BASE_HEADERS, b"accept", None),
        (b"accept", b"text/plain"),
        (b"accept", b"text/html"),
    )

    original = await query_cache_key(_request(headers=headers))
    reversed_key = await query_cache_key(_request(headers=reversed_headers))

    assert original != reversed_key


async def test_length_framing_prevents_cross_field_boundary_collisions() -> None:
    first = await query_cache_key(_request(query=b"a", body=b"bc"))
    second = await query_cache_key(_request(query=b"ab", body=b"c"))

    assert first != second


@pytest.mark.parametrize("private_name", [b"cookie", b"authorization"])
async def test_query_cache_key_rejects_private_requests_without_exposing_value(
    private_name: bytes,
) -> None:
    secret = b"private-credential-value"
    headers = (*_BASE_HEADERS, (private_name, secret))

    with pytest.raises(ValueError, match="private requests must bypass") as caught:
        await query_cache_key(_request(headers=headers))

    assert "bypass" in str(caught.value)
    assert secret.decode() not in str(caught.value)


async def test_query_cache_key_checks_every_private_header_field() -> None:
    headers = (*_BASE_HEADERS, (b"cookie", b""), (b"cookie", b"session=secret"))
    with pytest.raises(ValueError, match="private requests must bypass"):
        await query_cache_key(_request(headers=headers))


async def test_query_cache_key_enforces_existing_request_body_limit() -> None:
    with pytest.raises(PayloadTooLarge):
        await query_cache_key(_request(body=b"12345", max_body_size=4))


@pytest.mark.parametrize("vary_header", ["", "bad header", "x-snowman-☃"])
async def test_query_cache_key_rejects_invalid_vary_header_names(vary_header: str) -> None:
    with pytest.raises(ValueError, match="vary header"):
        await query_cache_key(_request(), vary_headers=(vary_header,))


async def test_query_cache_key_rejects_non_query_method() -> None:
    with pytest.raises(ValueError, match=r"requires request\.method == 'QUERY'"):
        await query_cache_key(_request(method="GET"))


@settings(max_examples=50, deadline=None)
@given(left=st.binary(max_size=256), right=st.binary(max_size=256))
def test_distinct_exact_bodies_have_distinct_query_cache_keys(left: bytes, right: bytes) -> None:
    assume(left != right)
    left_key = asyncio.run(query_cache_key(_request(body=left)))
    right_key = asyncio.run(query_cache_key(_request(body=right)))
    assert left_key != right_key


def test_query_cache_key_is_stable_across_process_hash_seeds() -> None:
    script = """
import asyncio
from chirp.cache.key import query_cache_key
from chirp.http.request import Request

body = b'{"term":"stable"}'
sent = False
async def receive():
    global sent
    if sent:
        return {"type": "http.disconnect"}
    sent = True
    return {"type": "http.request", "body": body, "more_body": False}

scope = {
    "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
    "method": "QUERY", "path": "/search", "raw_path": b"/search",
    "query_string": b"page=2", "root_path": "",
    "headers": [(b"content-type", b"application/json"),
                (b"accept", b"text/html"), (b"x-tenant", b"public")],
    "server": ("testserver", 80), "client": ("127.0.0.1", 1),
}
request = Request.from_asgi(scope, receive)
print(asyncio.run(query_cache_key(request, vary_headers=("x-tenant",))))
"""

    def run(seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        return subprocess.check_output(
            [sys.executable, "-c", script],
            text=True,
            env=env,
        ).strip()

    assert run("1") == run("8675309")


async def test_query_cache_key_has_no_shared_mutable_state() -> None:
    def factory() -> Request:
        return _request(body=b"same")

    keys = await asyncio.gather(*(query_cache_key(factory()) for _ in range(100)))
    assert len(set(keys)) == 1
