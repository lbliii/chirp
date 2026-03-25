"""Tests for AllowedHostsMiddleware."""

import pytest

from chirp.middleware.allowed_hosts import AllowedHostsMiddleware


class FakeRequest:
    def __init__(self, host="localhost"):
        self.headers = {"host": host}


async def ok_next(request):
    from chirp.http.response import Response
    return Response("ok", status=200)


@pytest.mark.asyncio
async def test_allow_all():
    mw = AllowedHostsMiddleware(("*",))
    resp = await mw(FakeRequest("anything.com"), ok_next)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_exact_match():
    mw = AllowedHostsMiddleware(("example.com",))
    resp = await mw(FakeRequest("example.com"), ok_next)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_reject_mismatch():
    mw = AllowedHostsMiddleware(("example.com",))
    resp = await mw(FakeRequest("evil.com"), ok_next)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_subdomain_wildcard():
    mw = AllowedHostsMiddleware((".example.com",))
    resp = await mw(FakeRequest("sub.example.com"), ok_next)
    assert resp.status == 200
    # Also matches the bare domain
    resp = await mw(FakeRequest("example.com"), ok_next)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_strip_port():
    mw = AllowedHostsMiddleware(("localhost",))
    resp = await mw(FakeRequest("localhost:8000"), ok_next)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_debug_message():
    mw = AllowedHostsMiddleware(("example.com",), debug=True)
    resp = await mw(FakeRequest("evil.com"), ok_next)
    assert resp.status == 400
    assert "evil.com" in resp.body
