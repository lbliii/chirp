"""Request-scoped context carried into ALL streamed renders.

One shared capture-then-re-establish path carries the request, auth user, CSRF
token, and ``g`` into deferred ``Suspense`` blocks, ``Stream`` generators, and
``EventStream`` (SSE) generators — so ``get_request()`` / ``get_user()`` /
``current_user()`` / ``get_csrf_token()`` / ``g`` work identically across all
three, even though the handler ``finally`` resets those ContextVars before the
streamed body drains.

SSE identity is pinned at connect time (the captured snapshot) for the life of
the connection; these tests assert that pinning and that vars reset cleanly
after the drain so a later unrelated request never sees a stream's identity.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from chirp import App, AppConfig, Stream, Suspense
from chirp.context import g, get_request
from chirp.middleware.auth import (
    AnonymousUser,
    AuthConfig,
    AuthMiddleware,
    User,
    current_user,
    get_user,
)
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware, get_csrf_token
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.realtime.events import EventStream
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeUser:
    id: str
    name: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()


_USERS: dict[str, FakeUser] = {
    "alice": FakeUser(id="alice", name="alice"),
    "bob": FakeUser(id="bob", name="bob"),
}
_TOKENS: dict[str, FakeUser] = {
    "tok_alice": _USERS["alice"],
    "tok_bob": _USERS["bob"],
}


async def _verify_token(token: str) -> FakeUser | None:
    return _TOKENS.get(token)


# Suspense template: deferred block renders whatever the awaitable resolved to.
_SUSPENSE_TEMPLATE = """\
<!DOCTYPE html>
<html><body>
<div id="panel">
{% block panel %}
  {% if value is deferred %}<span class="skeleton">LOADING</span>
  {% else %}<span class="loaded">VALUE:{{ value }}</span>{% end %}
{% end %}
</div>
</body></html>"""

# Stream template: a single value interpolated after a flush boundary.
_STREAM_TEMPLATE = """\
<!DOCTYPE html>
<html><body>
<header>SHELL</header>
{% flush %}
<p>STREAM-VALUE:{{ value }}</p>
</body></html>"""


def _write_templates(tmp_path: Path) -> Path:
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "suspense.html").write_text(_SUSPENSE_TEMPLATE)
    (tdir / "stream.html").write_text(_STREAM_TEMPLATE)
    return tdir


# ---------------------------------------------------------------------------
# Suspense — g carried into deferred blocks
# ---------------------------------------------------------------------------


class TestSuspenseCarriesG:
    async def test_deferred_block_reads_g_value(self, tmp_path: Path) -> None:
        """A deferred awaitable that reads g (set in the handler) renders it."""
        tdir = _write_templates(tmp_path)
        app = App(config=AppConfig(template_dir=tdir, worker_mode="async"))

        @app.route("/suspense")
        def suspense():
            g.greeting = "hello-from-g"

            async def _load() -> str:
                # Runs after the handler finally reset g — must see the snapshot.
                return g.greeting

            return Suspense("suspense.html", value=_load())

        async with TestClient(app) as client:
            resp = await client.get("/suspense")

        assert "VALUE:hello-from-g" in resp.text

    async def test_deferred_block_can_write_g_with_empty_snapshot(self, tmp_path: Path) -> None:
        """An empty-dict g snapshot still installs a writable store (no crash)."""
        tdir = _write_templates(tmp_path)
        app = App(config=AppConfig(template_dir=tdir, worker_mode="async"))

        @app.route("/suspense")
        def suspense():
            # Touch g so the store is non-None but empty-ish, then the deferred
            # block writes a NEW key to g — must not crash.
            g.touched = True

            async def _load() -> str:
                g.written_in_defer = "ok"
                return g.written_in_defer

            return Suspense("suspense.html", value=_load())

        async with TestClient(app) as client:
            resp = await client.get("/suspense")

        assert "VALUE:ok" in resp.text


# ---------------------------------------------------------------------------
# Stream — g carried into the generator; reset after drain
# ---------------------------------------------------------------------------


class TestStreamCarriesG:
    async def test_stream_reads_g_value(self, tmp_path: Path) -> None:
        """A Stream render reads a g value set in the handler."""
        tdir = _write_templates(tmp_path)
        app = App(config=AppConfig(template_dir=tdir, worker_mode="async"))

        @app.route("/stream")
        def stream():
            g.token = "g-stream-val"
            # Read g eagerly into context: the off-loop worker copies the loop's
            # restored contextvars, so g is live during render either way.
            return Stream("stream.html", value=g.token)

        async with TestClient(app) as client:
            resp = await client.get("/stream")

        assert "STREAM-VALUE:g-stream-val" in resp.text

    async def test_g_reset_after_stream_drain(self, tmp_path: Path) -> None:
        """g is reset after the drain — a later unrelated request raises on read."""
        tdir = _write_templates(tmp_path)
        app = App(config=AppConfig(template_dir=tdir, worker_mode="async"))

        @app.route("/stream")
        def stream():
            g.token = "first-request"
            return Stream("stream.html", value=g.token)

        @app.route("/plain")
        def plain():
            # Fresh request: g must NOT carry the stream's value.
            with pytest.raises(AttributeError):
                _ = g.token
            return "clean"

        async with TestClient(app) as client:
            r1 = await client.get("/stream")
            assert "STREAM-VALUE:first-request" in r1.text
            r2 = await client.get("/plain")
            assert r2.text == "clean"


# ---------------------------------------------------------------------------
# EventStream (SSE) — request / user / csrf / g all carried
# ---------------------------------------------------------------------------


class TestEventStreamCarriesContext:
    async def test_get_user_returns_connect_time_user(self) -> None:
        """get_user() inside the SSE generator returns the authenticated user."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/events")
        def events():
            async def gen():
                user = get_user()
                yield f"user:{user.id}:auth:{user.is_authenticated}"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse(
                "/events",
                headers={"Authorization": "Bearer tok_alice"},
                max_events=1,
            )

        assert result.events[0].data == "user:alice:auth:True"

    async def test_current_user_returns_connect_time_user(self) -> None:
        """current_user() inside the SSE generator returns the authed user."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/events")
        def events():
            async def gen():
                yield f"name:{current_user().id}"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse(
                "/events",
                headers={"Authorization": "Bearer tok_bob"},
                max_events=1,
            )

        assert result.events[0].data == "name:bob"

    async def test_anonymous_request_returns_anonymous_user(self) -> None:
        """No credentials -> get_user() returns AnonymousUser, never raises."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/events")
        def events():
            async def gen():
                user = get_user()
                yield f"anon:{isinstance(user, AnonymousUser)}:auth:{user.is_authenticated}"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert result.events[0].data == "anon:True:auth:False"

    async def test_get_request_returns_the_request(self) -> None:
        """get_request() inside the SSE generator returns the connecting request."""
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                req = get_request()
                yield f"path:{req.path}"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert result.events[0].data == "path:/events"

    async def test_get_csrf_token_returns_the_token(self) -> None:
        """get_csrf_token() inside the SSE generator returns the live token."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(CSRFMiddleware(CSRFConfig()))

        captured: list[str] = []

        @app.route("/events")
        def events():
            captured.append(get_csrf_token())

            async def gen():
                yield f"csrf:{get_csrf_token()}"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert captured, "handler should have a live CSRF token"
        assert result.events[0].data == f"csrf:{captured[0]}"

    async def test_g_read_inside_generator(self) -> None:
        """A g value set in the handler is readable inside the SSE generator."""
        app = App()

        @app.route("/events")
        def events():
            g.channel = "ticker-42"

            async def gen():
                yield f"g:{g.channel}"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert result.events[0].data == "g:ticker-42"


# ---------------------------------------------------------------------------
# Free-threading isolation — concurrent SSE streams must not cross-contaminate
# ---------------------------------------------------------------------------


class TestSSEIsolation:
    async def test_concurrent_streams_different_users(self) -> None:
        """Two SSE streams for different users see their own get_user()."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        # A barrier so both generators are live concurrently before either
        # reads get_user() — proving no cross-task contamination.
        barrier = asyncio.Barrier(2)

        @app.route("/events")
        def events():
            async def gen():
                await barrier.wait()
                user = get_user()
                yield f"user:{user.id}"

            return EventStream(gen())

        async with TestClient(app) as client:
            results = await asyncio.gather(
                client.sse(
                    "/events",
                    headers={"Authorization": "Bearer tok_alice"},
                    max_events=1,
                ),
                client.sse(
                    "/events",
                    headers={"Authorization": "Bearer tok_bob"},
                    max_events=1,
                ),
            )

        datas = {r.events[0].data for r in results}
        assert datas == {"user:alice", "user:bob"}

    async def test_user_reset_after_close(self) -> None:
        """After an SSE stream closes, a later request does not see its user.

        The auth user is re-established via a token-based ContextVar reset in
        the SSE producer task's ``finally`` (mirroring the CSP-nonce handling),
        so it cannot bleed into a later unrelated request — even though both run
        on the same event loop under ``TestClient``.

        (``g`` is a *mutable dict* in a ContextVar; under ``TestClient`` a child
        task can share the parent's underlying dict object, so this test asserts
        the user — which uses a clean token reset — not the g store.)
        """
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/events")
        def events():
            async def gen():
                yield f"user:{get_user().id}"

            return EventStream(gen())

        @app.route("/check")
        def check():
            # Anonymous (no token) — must NOT inherit the stream's alice.
            user = get_user()
            return f"check:{user.id or 'anon'}:auth:{user.is_authenticated}"

        async with TestClient(app) as client:
            sse_result = await client.sse(
                "/events",
                headers={"Authorization": "Bearer tok_alice"},
                max_events=1,
            )
            assert sse_result.events[0].data == "user:alice"

            resp = await client.get("/check")

        assert resp.text == "check:anon:auth:False"


def test_user_protocol_smoke() -> None:
    """FakeUser satisfies the User protocol (guards the fixture)."""
    assert isinstance(_USERS["alice"], User)
