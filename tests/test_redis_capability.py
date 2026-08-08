"""Live Redis capability and failure-path proof (#906).

Default installs keep ``chirp[redis]`` optional. The specialized
``redis-capability`` CI lane installs the extra, starts Redis, and sets
``CHIRP_REQUIRE_REDIS=1`` so package/service absence fails instead of
skipping. These tests exercise real Redis I/O — not import-only or mocked
clients.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

from chirp import App
from chirp.cache.backends.redis import RedisCacheBackend
from chirp.http.response import Response
from chirp.middleware.auth_rate_limit import (
    AuthRateLimitConfig,
    AuthRateLimitMiddleware,
    redis_rate_limit_backend,
)
from chirp.middleware.sessions import (
    RedisSessionStore,
    SessionConfig,
    SessionMiddleware,
    get_session,
)
from chirp.testing import TestClient
from tests.helpers.auth import extract_session_cookie
from tests.helpers.redis_capability import (
    _REQUIRE_REDIS_ENV,
    ensure_live_redis,
    ensure_redis_package,
    redis_package_available,
)

_REDIS_OUTAGE_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
)

# Closed local port — deterministic "Redis unavailable" without flaky network.
_UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"


class _StubRequest:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.cookies: dict[str, str] = cookies or {}


@pytest.mark.issue(906)
def test_capability_lane_requires_redis_package() -> None:
    """redis-capability CI must install chirp[redis]; default installs stay optional."""
    if os.environ.get(_REQUIRE_REDIS_ENV) != "1":
        return
    assert redis_package_available(), "chirp[redis] / redis missing in redis-capability lane"


@pytest.mark.issue(906)
async def test_live_redis_session_roundtrip() -> None:
    """RedisSessionStore persists session data through a real Redis round-trip."""
    url = await ensure_live_redis()
    prefix = f"chirp:ci906:session:{uuid.uuid4().hex}:"
    store = RedisSessionStore(
        SessionConfig(secret_key="redis-capability-secret"),
        url,
        key_prefix=prefix,
    )

    app = App()
    app.add_middleware(
        SessionMiddleware(SessionConfig(secret_key="redis-capability-secret", store=store))
    )

    @app.route("/set")
    def set_session():
        session = get_session()
        session["name"] = "alice"
        return "set"

    @app.route("/get")
    def get_name():
        session = get_session()
        return f"name={session.get('name', 'none')}"

    async with TestClient(app) as client:
        set_resp = await client.get("/set")
        assert set_resp.status == 200
        cookie = extract_session_cookie(set_resp, "chirp_session")
        assert cookie is not None

        get_resp = await client.get(
            "/get",
            headers={"Cookie": f"chirp_session={cookie}"},
        )
        assert get_resp.status == 200
        assert get_resp.text == "name=alice"


@pytest.mark.issue(906)
async def test_live_redis_cache_get_set() -> None:
    """RedisCacheBackend get/set against a live Redis service."""
    url = await ensure_live_redis()
    backend = RedisCacheBackend(url)
    await backend.connect()
    try:
        key = f"chirp:ci906:cache:{uuid.uuid4().hex}"
        await backend.set(key, b"capability-proof", ttl=30)
        assert await backend.get(key) == b"capability-proof"
        await backend.delete(key)
        assert await backend.get(key) is None
    finally:
        await backend.disconnect()


@pytest.mark.issue(906)
async def test_live_redis_rate_limit_blocks_after_threshold() -> None:
    """redis_rate_limit_backend enforces limits across requests via live Redis."""
    url = await ensure_live_redis()
    prefix = f"chirp:ci906:ratelimit:{uuid.uuid4().hex}:"
    backend = redis_rate_limit_backend(url, key_prefix=prefix)

    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(
                requests=2,
                window_seconds=60,
                block_seconds=120,
                paths=("/login",),
                backend=backend,
            )
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-forwarded-for": "203.0.113.50",
        }
        r1 = await client.post("/login", body=b"a=1", headers=headers)
        r2 = await client.post("/login", body=b"a=1", headers=headers)
        r3 = await client.post("/login", body=b"a=1", headers=headers)

    assert r1.status == 200
    assert r2.status == 200
    assert r3.status == 429
    assert r3.header("retry-after") is not None


@pytest.mark.issue(906)
async def test_unavailable_redis_session_save_fails_loudly() -> None:
    """Bounded outage: unreachable Redis fails the save path (no silent success)."""
    ensure_redis_package()
    store = RedisSessionStore(
        SessionConfig(secret_key="redis-outage-secret"),
        _UNREACHABLE_REDIS_URL,
        key_prefix=f"chirp:ci906:outage:{uuid.uuid4().hex}:",
    )

    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    with pytest.raises((*_REDIS_OUTAGE_ERRORS, RedisConnectionError, RedisTimeoutError)):
        await store.save(Response(b"ok"), {"name": "alice"})


@pytest.mark.issue(906)
async def test_unavailable_redis_rate_limit_fails_loudly() -> None:
    """Bounded outage: unreachable Redis fails rate-limit check (no silent allow)."""
    ensure_redis_package()
    backend = redis_rate_limit_backend(
        _UNREACHABLE_REDIS_URL,
        key_prefix=f"chirp:ci906:outage-rl:{uuid.uuid4().hex}:",
    )

    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    with pytest.raises((*_REDIS_OUTAGE_ERRORS, RedisConnectionError, RedisTimeoutError)):
        await backend.check_and_update(
            "client-1",
            time.time(),
            requests=5,
            window_seconds=60,
            block_seconds=30,
        )
