"""Tests for app.kick_user (#372)."""

from __future__ import annotations

import asyncio

import pytest

from chirp import App
from chirp.middleware.auth import AuthConfig, AuthMiddleware, get_user, login
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.pages.reactive import BlockRef, ConnectionInfo, ReactiveBus
from chirp.pages.reactive.index import DependencyIndex
from chirp.pages.reactive.stream import reactive_stream
from chirp.realtime.events import EventStream
from chirp.security.audit import SecurityEvent, set_security_event_sink
from chirp.testing import TestClient
from tests.helpers.auth import extract_session_cookie
from tests.test_auth import _USERS, FakeUser, _load_user


def _dep_index() -> DependencyIndex:
    index = DependencyIndex()
    index.register("data", BlockRef(template_name="page.html", block_name="content"))
    return index


@pytest.mark.issue(372)
class TestKickUser:
    async def test_kick_user_closes_registered_bus(self) -> None:
        app = App()
        bus = ReactiveBus()
        app.register_reactive_bus(bus)
        conn = ConnectionInfo(session_id="s1", user_id="alice")
        stopped = asyncio.Event()

        async def run_sub() -> None:
            async for _ in bus.subscribe("live", connection=conn):
                pass
            stopped.set()

        task = asyncio.create_task(run_sub())
        await asyncio.sleep(0.01)
        assert app.kick_user("alice") == 1
        await asyncio.wait_for(stopped.wait(), timeout=1.0)
        bus.close("live")
        await task

    async def test_kick_user_emits_security_event(self) -> None:
        events: list[SecurityEvent] = []

        def _sink(event: SecurityEvent) -> None:
            events.append(event)

        set_security_event_sink(_sink)
        try:
            app = App()
            bus = ReactiveBus()
            app.register_reactive_bus(bus)
            conn = ConnectionInfo(session_id="s1", user_id="alice")

            async def run_sub() -> None:
                async for _ in bus.subscribe("live", connection=conn):
                    pass

            task = asyncio.create_task(run_sub())
            await asyncio.sleep(0.01)
            app.kick_user("alice")
            bus.close("live")
            await task
            kicked = [e for e in events if e.name == "sse.connection.kicked"]
            assert len(kicked) == 1
            assert kicked[0].user_id == "alice"
            assert kicked[0].details == {"closed": 1}
        finally:
            set_security_event_sink(None)

    async def test_kick_user_leaves_other_users_unaffected(self) -> None:
        app = App()
        bus = ReactiveBus()
        app.register_reactive_bus(bus)
        conn_alice = ConnectionInfo(session_id="s1", user_id="alice")
        conn_bob = ConnectionInfo(session_id="s2", user_id="bob")
        alice_stopped = asyncio.Event()

        async def alice_sub() -> None:
            async for _ in bus.subscribe("live", connection=conn_alice):
                pass
            alice_stopped.set()

        async def bob_sub() -> None:
            async for _ in bus.subscribe("live", connection=conn_bob):
                return

        alice_task = asyncio.create_task(alice_sub())
        bob_task = asyncio.create_task(bob_sub())
        await asyncio.sleep(0.01)
        app.kick_user("alice")
        await asyncio.wait_for(alice_stopped.wait(), timeout=1.0)
        assert not bob_task.done()
        bus.close("live")
        await alice_task
        await bob_task

    async def test_revoke_kick_reconnect_reauth(self) -> None:
        """After kick, reconnect re-pins the user from current auth middleware state."""
        live_perms: dict[str, frozenset[str]] = {"1": frozenset({"admin"})}

        async def _load(user_id: str) -> FakeUser | None:
            base = await _load_user(user_id)
            if base is None:
                return None
            return FakeUser(
                id=base.id,
                name=base.name,
                permissions=live_perms.get(base.id, frozenset()),
            )

        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(AuthMiddleware(AuthConfig(load_user=_load)))
        bus = ReactiveBus()
        app.register_reactive_bus(bus)
        index = _dep_index()
        pinned: list[frozenset[str]] = []

        @app.route("/do-login")
        def do_login():
            login(_USERS["1"])
            return "ok"

        @app.route("/live")
        def live() -> EventStream:
            user = get_user()
            pinned.append(user.permissions)
            return reactive_stream(
                bus,
                scope="live",
                index=index,
                context_builder=lambda: {"data": "x"},
                connection=ConnectionInfo(session_id="sess", user_id=user.id),
            )

        async with TestClient(app) as client:
            r_login = await client.get("/do-login")
            cookie = extract_session_cookie(r_login, "chirp_session")
            assert cookie is not None
            headers = {"Cookie": f"chirp_session={cookie}", "Accept": "text/event-stream"}

            r1 = await client.get("/live", headers=headers)
            assert r1.status == 200
            assert pinned[-1] == frozenset({"admin"})

            live_perms["1"] = frozenset()
            app.kick_user("1")

            r2 = await client.get("/live", headers=headers)
            assert r2.status == 200
            assert pinned[-1] == frozenset()

        bus.close("live")
