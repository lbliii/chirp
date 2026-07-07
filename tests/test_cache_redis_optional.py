"""Optional Redis cache dependency guidance and connected path (#531)."""

from __future__ import annotations

import builtins
from types import SimpleNamespace

import pytest

from chirp.cache.backends.redis import RedisCacheBackend

pytestmark = pytest.mark.issue(531)


async def test_redis_cache_missing_extra_has_actionable_install_guidance(monkeypatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "redis.asyncio":
            raise ImportError("redis absent")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    backend = RedisCacheBackend()

    with pytest.raises(RuntimeError, match=r"pip install 'bengal-chirp\[redis\]'"):
        await backend.connect()


async def test_redis_cache_present_extra_builds_async_client(monkeypatch) -> None:
    client = object()
    asyncio_module = SimpleNamespace(from_url=lambda url: (url, client))
    redis_module = SimpleNamespace(asyncio=asyncio_module)
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "redis.asyncio":
            return redis_module
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    backend = RedisCacheBackend("redis://cache.example/3")

    await backend.connect()

    assert backend._redis == ("redis://cache.example/3", client)
