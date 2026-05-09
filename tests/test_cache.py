"""Tests for the caching framework."""

import asyncio
import inspect

import pytest

from chirp.cache import DeferredCache, create_backend, get_cache, set_cache
from chirp.cache.backends.memory import MemoryCacheBackend
from chirp.cache.backends.null import NullCacheBackend
from chirp.cache.key import default_cache_key


async def _resolve(value):
    if inspect.isawaitable(value):
        return await value
    return value


@pytest.mark.asyncio
async def test_memory_backend_basic():
    backend = MemoryCacheBackend()
    await backend.set("key1", b"value1")
    assert await backend.get("key1") == b"value1"


@pytest.mark.asyncio
async def test_memory_backend_miss():
    backend = MemoryCacheBackend()
    assert await backend.get("nonexistent") is None


@pytest.mark.asyncio
async def test_memory_backend_delete():
    backend = MemoryCacheBackend()
    await backend.set("key1", b"value1")
    await backend.delete("key1")
    assert await backend.get("key1") is None


@pytest.mark.asyncio
async def test_memory_backend_clear():
    backend = MemoryCacheBackend()
    await backend.set("a", b"1")
    await backend.set("b", b"2")
    await backend.clear()
    assert await backend.get("a") is None
    assert await backend.get("b") is None


@pytest.mark.asyncio
async def test_memory_backend_ttl_expired():
    backend = MemoryCacheBackend()
    # Set with very short TTL — we'll monkey-patch time
    await backend.set("key", b"val", ttl=1)
    # Manually expire it
    key_data = backend._store["key"]
    backend._store["key"] = (key_data[0], 0.0001)  # Already expired
    assert await backend.get("key") is None


@pytest.mark.asyncio
async def test_null_backend():
    backend = NullCacheBackend()
    await backend.set("key", b"value")
    assert await backend.get("key") is None
    await backend.delete("key")
    await backend.clear()


def test_create_backend_memory():
    backend = create_backend("memory")
    assert isinstance(backend, MemoryCacheBackend)


def test_create_backend_null():
    backend = create_backend("null")
    assert isinstance(backend, NullCacheBackend)


def test_create_backend_unknown():
    with pytest.raises(ValueError, match="Unknown cache backend"):
        create_backend("unknown")


def test_cache_key_basic():
    class FakeReq:
        method = "GET"
        path = "/products"
        query_string = ""
        query = None

    key = default_cache_key(FakeReq())
    assert key.startswith("chirp:GET:/products:")


def test_cache_key_includes_query_string():
    class FakeQuery:
        _raw = b"page=2&q=forum"

    class FakeReq:
        method = "GET"
        path = "/threads"
        query = FakeQuery()

    class OtherReq:
        method = "GET"
        path = "/threads"
        query_string = "page=3&q=forum"
        query = None

    assert default_cache_key(FakeReq()) != default_cache_key(OtherReq())


def test_cache_key_includes_htmx_shape():
    class FullReq:
        method = "GET"
        path = "/threads"
        query_string = ""
        query = None
        is_htmx = False
        is_boosted = False
        is_history_restore = False
        htmx_target_id = None

    class FragmentReq:
        method = "GET"
        path = "/threads"
        query_string = ""
        query = None
        is_htmx = True
        is_boosted = False
        is_history_restore = False
        htmx_target_id = "thread-list"

    assert default_cache_key(FullReq()) != default_cache_key(FragmentReq())


def test_get_cache_default():
    assert get_cache() is None


def test_set_and_get_cache():
    backend = MemoryCacheBackend()
    set_cache(backend)
    assert get_cache() is backend
    # Reset
    set_cache(None)


@pytest.mark.asyncio
async def test_deferred_cache_miss_then_hit():
    cache = DeferredCache(default_ttl=60)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return "fresh"

    first = cache.get_or_defer("profile", factory)
    assert inspect.isawaitable(first)
    assert await first == "fresh"

    second = cache.get_or_defer("profile", factory)
    assert second == "fresh"
    assert calls == 1


@pytest.mark.asyncio
async def test_deferred_cache_expires():
    cache = DeferredCache(default_ttl=0.01)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return f"value-{calls}"

    assert await _resolve(cache.get_or_defer("stats", factory)) == "value-1"
    await asyncio.sleep(0.02)
    assert await _resolve(cache.get_or_defer("stats", factory)) == "value-2"
    assert calls == 2


@pytest.mark.asyncio
async def test_deferred_cache_ttl_zero_bypasses_cache():
    cache = DeferredCache(default_ttl=60)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return calls

    assert await _resolve(cache.get_or_defer("live", factory, ttl=0)) == 1
    assert await _resolve(cache.get_or_defer("live", factory, ttl=0)) == 2


@pytest.mark.asyncio
async def test_deferred_cache_deduplicates_inflight_misses():
    cache = DeferredCache(default_ttl=60)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "shared"

    pending = [cache.get_or_defer("same", factory) for _ in range(10)]
    assert all(inspect.isawaitable(item) for item in pending)
    results = await asyncio.gather(*pending)

    assert results == ["shared"] * 10
    assert calls == 1
    assert cache.get_or_defer("same", factory) == "shared"


@pytest.mark.asyncio
async def test_deferred_cache_does_not_cache_exceptions():
    cache = DeferredCache(default_ttl=60)
    calls = 0

    async def failing_factory():
        nonlocal calls
        calls += 1
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError, match="upstream down"):
        await _resolve(cache.get_or_defer("fragile", failing_factory))

    async def successful_factory():
        nonlocal calls
        calls += 1
        return "recovered"

    assert await _resolve(cache.get_or_defer("fragile", successful_factory)) == "recovered"
    assert cache.get_or_defer("fragile", successful_factory) == "recovered"
    assert calls == 2


def test_deferred_cache_instances_are_isolated():
    cache_a = DeferredCache(default_ttl=60)
    cache_b = DeferredCache(default_ttl=60)

    async def factory_a():
        return "a"

    async def factory_b():
        return "b"

    assert asyncio.run(_resolve(cache_a.get_or_defer("same", factory_a))) == "a"
    assert asyncio.run(_resolve(cache_b.get_or_defer("same", factory_b))) == "b"
    assert cache_a.get_or_defer("same", factory_a) == "a"
    assert cache_b.get_or_defer("same", factory_b) == "b"


@pytest.mark.asyncio
async def test_deferred_cache_delete_and_clear():
    cache = DeferredCache(default_ttl=60)

    async def factory():
        return "value"

    assert await _resolve(cache.get_or_defer("one", factory)) == "value"
    cache.delete("one")
    assert await _resolve(cache.get_or_defer("one", factory)) == "value"

    assert await _resolve(cache.get_or_defer("two", factory)) == "value"
    cache.clear()
    assert await _resolve(cache.get_or_defer("two", factory)) == "value"


def test_deferred_cache_rejects_empty_key():
    cache = DeferredCache()

    async def factory():
        return "value"

    with pytest.raises(ValueError, match="non-empty string"):
        cache.get_or_defer("", factory)


@pytest.mark.asyncio
async def test_deferred_cache_closed_awaitable_releases_inflight():
    cache = DeferredCache(default_ttl=60)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return "value"

    pending = cache.get_or_defer("cancelled", factory)
    pending.close()

    with pytest.raises(RuntimeError, match="closed before it ran"):
        await pending

    assert await _resolve(cache.get_or_defer("cancelled", factory)) == "value"
    assert calls == 1


@pytest.mark.asyncio
async def test_deferred_cache_delete_drops_inflight_storage():
    cache = DeferredCache(default_ttl=60)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return f"value-{calls}"

    pending = cache.get_or_defer("dropped", factory)
    cache.delete("dropped")
    assert await _resolve(pending) == "value-1"

    assert await _resolve(cache.get_or_defer("dropped", factory)) == "value-2"
    assert calls == 2
