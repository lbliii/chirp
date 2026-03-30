"""Tests for CSP nonce middleware."""

import pytest

from chirp.middleware.csp_nonce import CSPNonceMiddleware, csp_nonce, get_csp_nonce


class FakeRequest:
    def __init__(self):
        self.headers = {"host": "localhost"}


def _get_header(resp, name):
    """Get a header value from a Response (tuple-based headers)."""
    name = name.lower()
    for k, v in resp.headers:
        if k.lower() == name:
            return v
    return ""


async def ok_next(request):
    from chirp.http.response import Response

    nonce = get_csp_nonce()
    return Response(f"nonce={nonce}", status=200, content_type="text/html")


@pytest.mark.asyncio
async def test_nonce_injected():
    mw = CSPNonceMiddleware()
    resp = await mw(FakeRequest(), ok_next)
    csp_header = _get_header(resp, "content-security-policy")
    assert "nonce-" in csp_header
    assert resp.status == 200


@pytest.mark.asyncio
async def test_nonce_unique_per_request():
    mw = CSPNonceMiddleware()
    resp1 = await mw(FakeRequest(), ok_next)
    resp2 = await mw(FakeRequest(), ok_next)
    csp1 = _get_header(resp1, "content-security-policy")
    csp2 = _get_header(resp2, "content-security-policy")
    assert csp1 != csp2


def test_csp_nonce_outside_request():
    assert csp_nonce() == ""


@pytest.mark.asyncio
async def test_template_globals():
    mw = CSPNonceMiddleware()
    assert "csp_nonce" in mw.template_globals


# --- CSP nonce must allow framework-required script origins ---


class TestNonceCSPAllowsFrameworkScripts:
    """When CSP nonces are enabled the policy must still permit CDN scripts.

    Chirp templates load htmx from unpkg.com and Alpine.js from
    cdn.jsdelivr.net.  A nonce-only policy would silently block those
    external scripts and break all htmx/JS functionality.
    """

    @pytest.mark.asyncio
    async def test_nonce_csp_allows_unpkg(self):
        mw = CSPNonceMiddleware()
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "https://unpkg.com" in csp

    @pytest.mark.asyncio
    async def test_nonce_csp_allows_jsdelivr(self):
        mw = CSPNonceMiddleware()
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "https://cdn.jsdelivr.net" in csp

    @pytest.mark.asyncio
    async def test_nonce_csp_has_nonce_and_origins(self):
        """script-src must contain the nonce AND the CDN origins together."""
        mw = CSPNonceMiddleware()
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "nonce-" in csp
        assert "https://unpkg.com" in csp
        assert "https://cdn.jsdelivr.net" in csp
