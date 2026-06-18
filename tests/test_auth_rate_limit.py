"""Tests for auth-focused rate limiting middleware."""

import pytest

from chirp import App
from chirp.middleware.auth_rate_limit import AuthRateLimitConfig, AuthRateLimitMiddleware
from chirp.testing import TestClient


@pytest.mark.anyio
async def test_limited_path_blocks_after_threshold() -> None:
    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(requests=2, window_seconds=60, block_seconds=120, paths=("/login",))
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-forwarded-for": "1.2.3.4",
        }
        r1 = await client.post("/login", body=b"a=1", headers=headers)
        r2 = await client.post("/login", body=b"a=1", headers=headers)
        r3 = await client.post("/login", body=b"a=1", headers=headers)

    assert r1.status == 200
    assert r2.status == 200
    assert r3.status == 429
    retry_after = r3.header("retry-after")
    assert retry_after is not None


@pytest.mark.anyio
async def test_non_limited_path_is_ignored() -> None:
    app = App()
    app.add_middleware(AuthRateLimitMiddleware(AuthRateLimitConfig(paths=("/login",))))

    @app.route("/health", methods=["POST"])
    async def health(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        response = await client.post(
            "/health",
            body=b"a=1",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert response.status == 200


@pytest.mark.anyio
async def test_limit_is_per_identity_key_via_trusted_header() -> None:
    # key_header now names a TRUSTED, server-set identity header consumed
    # verbatim (NOT an X-Forwarded-For override). Distinct identities get
    # distinct buckets.
    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(
                requests=1,
                window_seconds=60,
                block_seconds=120,
                paths=("/login",),
                key_header="x-api-key",
            )
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        common_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        first_id_1 = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-api-key": "tenant-a"},
        )
        second_id_1 = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-api-key": "tenant-a"},
        )
        first_id_2 = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-api-key": "tenant-b"},
        )

    assert first_id_1.status == 200
    assert second_id_1.status == 429
    assert first_id_2.status == 200


@pytest.mark.anyio
async def test_trusted_header_is_consumed_verbatim_not_comma_split() -> None:
    # A trusted identity header is used as-is — no first-comma split — so two
    # callers presenting the same header value share one bucket even when the
    # value happens to contain commas.
    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(
                requests=1,
                window_seconds=60,
                block_seconds=120,
                paths=("/login",),
                key_header="x-api-key",
            )
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        common_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        first = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-api-key": "a,b"},
        )
        # Same verbatim value → same bucket → blocked. (Old comma-split logic
        # would have keyed both off "a" too, but for the wrong reason.)
        second = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-api-key": "a,b"},
        )

    assert first.status == 200
    assert second.status == 429


@pytest.mark.anyio
async def test_forwarded_for_is_ignored_by_default() -> None:
    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(requests=1, window_seconds=60, block_seconds=120, paths=("/login",))
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        common_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        first = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-forwarded-for": "10.0.0.1"},
        )
        second = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-forwarded-for": "10.0.0.2"},
        )

    assert first.status == 200
    assert second.status == 429


@pytest.mark.issue(378)
@pytest.mark.anyio
async def test_spoofed_x_forwarded_for_cannot_evade_limit() -> None:
    # Acceptance: an attacker on one real client rotates a spoofed
    # X-Forwarded-For on every request to try to win a fresh bucket each time.
    # Keying off request.trusted_client_ip (the real peer) — never raw XFF —
    # means all attempts collapse to one bucket and the limiter still blocks.
    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(requests=2, window_seconds=60, block_seconds=120, paths=("/login",))
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        common_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        statuses = []
        for i in range(4):
            resp = await client.post(
                "/login",
                body=b"a=1",
                # Distinct spoofed first-hop on every attempt.
                headers={**common_headers, "x-forwarded-for": f"203.0.113.{i}"},
            )
            statuses.append(resp.status)

    # First two within the window pass; the rotating spoof does not earn a
    # fresh bucket, so the third+ are blocked.
    assert statuses == [200, 200, 429, 429]


def test_identity_key_ignores_spoofed_x_forwarded_for() -> None:
    # Unit-level proof of the invariant (TestClient hardcodes scope["client"],
    # so the spoof evasion is keyed at the property layer): the identity key is
    # stable across rotating raw X-Forwarded-For values for the same peer.
    from chirp.http.request import Request

    def make_request(xff: str) -> Request:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/login",
            "raw_path": b"/login",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"x-forwarded-for", xff.encode())],
            "server": ("localhost", 8000),
            "client": ("198.51.100.9", 5000),
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        return Request.from_asgi(scope, receive)

    mw = AuthRateLimitMiddleware(AuthRateLimitConfig())
    key_a = mw._identity_key(make_request("1.2.3.4"))
    key_b = mw._identity_key(make_request("5.6.7.8, 9.9.9.9"))

    assert key_a == key_b == "198.51.100.9"
