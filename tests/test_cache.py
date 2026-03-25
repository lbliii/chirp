"""Tests for the caching framework."""

import pytest

from chirp.cache import create_backend, get_cache, set_cache
from chirp.cache.backends.memory import MemoryCacheBackend
from chirp.cache.backends.null import NullCacheBackend
from chirp.cache.key import default_cache_key


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

    key = default_cache_key(FakeReq())
    assert key.startswith("chirp:GET:/products:")


def test_get_cache_default():
    assert get_cache() is None


def test_set_and_get_cache():
    backend = MemoryCacheBackend()
    set_cache(backend)
    assert get_cache() is backend
    # Reset
    set_cache(None)
