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
