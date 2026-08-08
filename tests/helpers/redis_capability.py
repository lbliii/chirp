"""Shared Redis optional-extra / live-service gates for capability proof (#906).

Local installs without ``chirp[redis]`` (or without a Redis server) skip.
The ``redis-capability`` CI lane sets ``CHIRP_REQUIRE_REDIS=1`` so absence
fails closed instead of silently skipping.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_REQUIRE_REDIS_ENV = "CHIRP_REQUIRE_REDIS"
_TEST_REDIS_URL_ENV = "CHIRP_TEST_REDIS_URL"
_DEFAULT_LIVE_URL = "redis://localhost:6379/15"


def redis_package_available() -> bool:
    """True when the optional ``redis`` package (asyncio API) is importable."""
    try:
        return importlib.util.find_spec("redis.asyncio") is not None
    except ModuleNotFoundError:
        return False


def ensure_redis_package() -> None:
    """Skip locally without chirp[redis]; fail when the capability lane requires it."""
    if redis_package_available():
        return
    if os.environ.get(_REQUIRE_REDIS_ENV) == "1":
        pytest.fail(
            "redis is required in the redis-capability CI lane "
            f"(set via {_REQUIRE_REDIS_ENV}=1); install chirp[redis]"
        )
    pytest.skip("requires the optional 'redis' extra")


def live_redis_url() -> str:
    """Redis URL for live capability tests (CI sets ``CHIRP_TEST_REDIS_URL``)."""
    return os.environ.get(_TEST_REDIS_URL_ENV) or _DEFAULT_LIVE_URL


async def ensure_live_redis() -> str:
    """Require package + a pingable Redis; fail closed under CHIRP_REQUIRE_REDIS=1."""
    ensure_redis_package()
    url = live_redis_url()
    import redis.asyncio as redis_async
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    client = redis_async.from_url(url)
    try:
        await client.ping()
    except (
        OSError,
        ConnectionError,
        TimeoutError,
        RedisConnectionError,
        RedisTimeoutError,
    ) as exc:
        if os.environ.get(_REQUIRE_REDIS_ENV) == "1":
            pytest.fail(
                f"live Redis is required in the redis-capability CI lane "
                f"({_TEST_REDIS_URL_ENV}={url!r}): {exc}"
            )
        pytest.skip(f"Redis not reachable at {url}: {exc}")
    finally:
        await client.aclose()
    return url
