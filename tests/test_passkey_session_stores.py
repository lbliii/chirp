"""Passkey challenge persistence across cookie and Redis session stores (#871).

The begin → finish ceremony stashes ``__passkey_challenge`` in the session.
Both ``CookieSessionStore`` and ``RedisSessionStore`` must round-trip that
security transaction key. Redis must still drop request-scoped ``__session_id``
bookkeeping without a blanket ``__*`` filter that also wiped timeout stamps
and the challenge.
"""

from __future__ import annotations

import importlib.util
import json
import time
from typing import Any

import pytest

from chirp.errors import ConfigurationError
from chirp.http.response import Response
from chirp.middleware.sessions import (
    _REDIS_EPHEMERAL_KEYS,
    CookieSessionStore,
    RedisSessionStore,
    SessionConfig,
    _session_var,
)
from chirp.security.passkeys import (
    CHALLENGE_SESSION_KEY,
    PasskeyChallengeError,
    _consume_challenge,
    _pop_challenge,
    _stash_challenge,
)

pytestmark = pytest.mark.issue(871)


def _redis_available() -> bool:
    try:
        return importlib.util.find_spec("redis.asyncio") is not None
    except ModuleNotFoundError:
        return False


_REDIS_AVAILABLE = _redis_available()


def _session_cookie_value(response: Response, name: str = "chirp_session") -> str:
    for cookie in response.cookies:
        if cookie.name == name:
            return cookie.value
    raise AssertionError(f"missing Set-Cookie for {name!r}")


class _StubRequest:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.cookies: dict[str, str] = cookies or {}


class _FakeRedisClient:
    """Minimal async Redis client for ``RedisSessionStore`` load/save."""

    def __init__(self, backend: dict[str, str]) -> None:
        self._backend = backend

    async def get(self, key: str) -> str | None:
        return self._backend.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._backend[key] = value

    async def delete(self, key: str) -> None:
        self._backend.pop(key, None)

    async def aclose(self) -> None:
        return None


def _patch_redis_backend(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Point ``redis.asyncio.from_url`` at an in-memory client (real package present)."""
    import redis.asyncio as redis_async

    backend: dict[str, str] = {}
    client = _FakeRedisClient(backend)
    monkeypatch.setattr(redis_async, "from_url", lambda _url: client)
    return backend


def _activate_session(data: dict[str, Any]):
    return _session_var.set(data)


# ---------------------------------------------------------------------------
# Cookie path — first-class, no Redis required
# ---------------------------------------------------------------------------


class TestCookieChallengeRoundtrip:
    async def test_challenge_survives_save_load_and_pops_once(self) -> None:
        store = CookieSessionStore(SessionConfig(secret_key="cookie-secret"))
        session: dict[str, Any] = {}
        token = _activate_session(session)
        try:
            _stash_challenge(b"cookie-challenge", ttl=300)
            assert CHALLENGE_SESSION_KEY in session
        finally:
            _session_var.reset(token)

        response = await store.save(Response(b"ok"), session)
        cookie = _session_cookie_value(response)

        loaded = await store.load(_StubRequest({"chirp_session": cookie}))  # type: ignore[arg-type]
        assert CHALLENGE_SESSION_KEY in loaded

        token = _activate_session(loaded)
        try:
            assert _pop_challenge() == b"cookie-challenge"
            assert _pop_challenge() is None  # replay rejected
            assert CHALLENGE_SESSION_KEY not in loaded
        finally:
            _session_var.reset(token)

    async def test_failed_finish_consumes_challenge(self) -> None:
        store = CookieSessionStore(SessionConfig(secret_key="cookie-secret"))
        session: dict[str, Any] = {}
        token = _activate_session(session)
        try:
            _stash_challenge(b"will-fail", ttl=300)
        finally:
            _session_var.reset(token)

        response = await store.save(Response(b"ok"), session)
        cookie = _session_cookie_value(response)

        loaded = await store.load(_StubRequest({"chirp_session": cookie}))  # type: ignore[arg-type]
        token = _activate_session(loaded)
        try:
            # Consume as finish would before verify — even a failed verify must
            # leave no reusable challenge (anti-replay).
            assert _consume_challenge() == b"will-fail"
            with pytest.raises(PasskeyChallengeError):
                _consume_challenge()
        finally:
            _session_var.reset(token)

    async def test_expired_challenge_rejected_and_removed(self) -> None:
        session: dict[str, Any] = {}
        token = _activate_session(session)
        try:
            _stash_challenge(b"stale", ttl=300)
            session[CHALLENGE_SESSION_KEY]["exp"] = time.time() - 1
            store = CookieSessionStore(SessionConfig(secret_key="cookie-secret"))
            response = await store.save(Response(b"ok"), dict(session))
        finally:
            _session_var.reset(token)

        cookie = _session_cookie_value(response)

        loaded = await store.load(_StubRequest({"chirp_session": cookie}))  # type: ignore[arg-type]
        token = _activate_session(loaded)
        try:
            assert _pop_challenge() is None
            assert CHALLENGE_SESSION_KEY not in loaded
        finally:
            _session_var.reset(token)


# ---------------------------------------------------------------------------
# Redis path — optional; preserves ceremony + timeout keys
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _REDIS_AVAILABLE, reason="requires the optional 'redis' extra")
class TestRedisChallengeRoundtrip:
    async def test_challenge_survives_begin_finish_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _patch_redis_backend(monkeypatch)
        store = RedisSessionStore(SessionConfig(secret_key="redis-secret"), "redis://localhost")

        session: dict[str, Any] = {"__session_id": "sess-1", "user": "alice"}
        token = _activate_session(session)
        try:
            _stash_challenge(b"redis-challenge", ttl=300)
        finally:
            _session_var.reset(token)

        response = await store.save(Response(b"ok"), session)
        cookie = _session_cookie_value(response)

        # Durable payload must keep the challenge and drop only ephemeral id.
        raw = next(iter(backend.values()))
        stored = json.loads(raw)
        assert CHALLENGE_SESSION_KEY in stored
        assert "__session_id" not in stored
        assert stored["user"] == "alice"

        loaded = await store.load(_StubRequest({"chirp_session": cookie}))  # type: ignore[arg-type]
        assert CHALLENGE_SESSION_KEY in loaded
        assert loaded.get("__session_id") == cookie

        token = _activate_session(loaded)
        try:
            assert _pop_challenge() == b"redis-challenge"
            assert _pop_challenge() is None  # replay
        finally:
            _session_var.reset(token)

        # Persist consumption so a second finish cannot reuse Redis state.
        await store.save(Response(b"ok"), loaded, regenerate_old_id=None)
        reloaded = await store.load(_StubRequest({"chirp_session": cookie}))  # type: ignore[arg-type]
        token = _activate_session(reloaded)
        try:
            with pytest.raises(PasskeyChallengeError):
                _consume_challenge()
        finally:
            _session_var.reset(token)

    async def test_failed_finish_consumes_challenge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_redis_backend(monkeypatch)
        store = RedisSessionStore(SessionConfig(secret_key="redis-secret"), "redis://localhost")

        session: dict[str, Any] = {}
        token = _activate_session(session)
        try:
            _stash_challenge(b"fail-once", ttl=300)
        finally:
            _session_var.reset(token)

        response = await store.save(Response(b"ok"), session)
        cookie = _session_cookie_value(response)

        loaded = await store.load(_StubRequest({"chirp_session": cookie}))  # type: ignore[arg-type]
        token = _activate_session(loaded)
        try:
            assert _consume_challenge() == b"fail-once"
            with pytest.raises(PasskeyChallengeError):
                _consume_challenge()
        finally:
            _session_var.reset(token)

    async def test_expired_challenge_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_redis_backend(monkeypatch)
        store = RedisSessionStore(SessionConfig(secret_key="redis-secret"), "redis://localhost")

        session: dict[str, Any] = {}
        token = _activate_session(session)
        try:
            _stash_challenge(b"expired", ttl=300)
            session[CHALLENGE_SESSION_KEY]["exp"] = time.time() - 1
        finally:
            _session_var.reset(token)

        response = await store.save(Response(b"ok"), session)
        cookie = _session_cookie_value(response)

        loaded = await store.load(_StubRequest({"chirp_session": cookie}))  # type: ignore[arg-type]
        token = _activate_session(loaded)
        try:
            assert _pop_challenge() is None
            assert CHALLENGE_SESSION_KEY not in loaded
        finally:
            _session_var.reset(token)

    async def test_timeout_stamps_persist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``__created_at`` / ``__last_seen_at`` must not be blanketed away."""
        backend = _patch_redis_backend(monkeypatch)
        cfg = SessionConfig(
            secret_key="redis-secret",
            idle_timeout_seconds=3600,
            absolute_timeout_seconds=86400,
        )
        store = RedisSessionStore(cfg, "redis://localhost")
        now = time.time()
        session = {
            "__session_id": "sess-timeout",
            cfg.created_at_key: now,
            cfg.last_seen_at_key: now,
            "cart": 1,
        }
        await store.save(Response(b"ok"), session)
        stored = json.loads(next(iter(backend.values())))
        assert cfg.created_at_key in stored
        assert cfg.last_seen_at_key in stored
        assert "__session_id" not in stored
        assert stored["cart"] == 1


# ---------------------------------------------------------------------------
# Filtering contract + optional-dep guidance
# ---------------------------------------------------------------------------


def test_redis_ephemeral_keys_are_session_id_only() -> None:
    assert frozenset({"__session_id"}) == _REDIS_EPHEMERAL_KEYS
    assert CHALLENGE_SESSION_KEY not in _REDIS_EPHEMERAL_KEYS
    assert not CHALLENGE_SESSION_KEY.startswith("__session")


def test_redis_store_missing_extra_has_install_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None):
        if name == "redis.asyncio":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    with pytest.raises(ConfigurationError, match=r"pip install chirp\[redis\]"):
        RedisSessionStore(SessionConfig(secret_key="s"), "redis://localhost")
