"""Behavior tests for the optimistic_apply example.

The optimistic paint/confirm/revert is client-side and verified in a real
browser by ``test_browser_smoke.py``; the framework guardrail in
``tests/test_islands.py`` proves only the zero-server-state boundary, not the
client behavior. These tests assert the SERVER surface: the mount renders, the
mutation returns the authoritative fragment, and the failing endpoint does not
swap.
"""

import pytest

from chirp.testing import TestClient

from .app import STATE, app


@pytest.fixture(autouse=True)
def _reset_state():
    STATE["liked"] = False
    STATE["count"] = 42


async def test_index_renders_optimistic_mount() -> None:
    async with TestClient(app) as client:
        res = await client.get("/")
        assert res.status == 200
        assert 'data-island-primitive="optimistic_apply"' in res.text
        assert 'id="like-btn"' in res.text
        # the islands runtime (with the blessed adapter) is injected
        assert 'data-chirp="islands"' in res.text


async def test_toggle_like_returns_authoritative_fragment() -> None:
    async with TestClient(app) as client:
        res = await client.post("/toggle-like")
        assert res.status == 200
        assert "Liked" in res.text
        assert ">43<" in res.text  # 42 -> 43
        assert 'data-island-primitive="optimistic_apply"' in res.text


async def test_save_broken_does_not_succeed() -> None:
    async with TestClient(app) as client:
        res = await client.post("/save-broken")
        assert res.status == 503
