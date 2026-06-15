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
    async def test_nonce_csp_no_unsafe_eval_by_default(self):
        """Default CSP should not include unsafe-eval (opt-in only)."""
        mw = CSPNonceMiddleware()
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "'unsafe-eval'" not in csp

    @pytest.mark.asyncio
    async def test_nonce_csp_unsafe_eval_when_opted_in(self):
        """Alpine.js standard build needs unsafe-eval; opt-in via constructor."""
        mw = CSPNonceMiddleware(unsafe_eval=True)
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "'unsafe-eval'" in csp

    @pytest.mark.asyncio
    async def test_nonce_csp_has_nonce_and_origins(self):
        """script-src must contain the nonce AND the CDN origins together."""
        mw = CSPNonceMiddleware()
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "nonce-" in csp
        assert "https://unpkg.com" in csp
        assert "https://cdn.jsdelivr.net" in csp

    @pytest.mark.asyncio
    @pytest.mark.issue(233)
    async def test_no_style_src_by_default(self):
        """Default CSP emits no style-src directive (opt-in only)."""
        mw = CSPNonceMiddleware()
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "style-src" not in csp

    @pytest.mark.asyncio
    @pytest.mark.issue(233)
    async def test_style_unsafe_inline_when_opted_in(self):
        """Alpine x-show writes un-nonceable inline styles; opt-in via constructor
        appends style-src 'self' 'unsafe-inline', scoped to style-src only."""
        mw = CSPNonceMiddleware(style_unsafe_inline=True)
        resp = await mw(FakeRequest(), ok_next)
        csp = _get_header(resp, "content-security-policy")
        assert "style-src 'self' 'unsafe-inline'" in csp
        # The relaxation is scoped to style-src — script-src stays nonce-only.
        script_directive = next(
            (d for d in csp.split(";") if d.strip().startswith("script-src")), ""
        )
        assert "'unsafe-inline'" not in script_directive


# --- StreamingResponse carries the live nonce for the sender (#181) ---


@pytest.mark.asyncio
async def test_streaming_response_carries_nonce():
    """The middleware stamps the live nonce onto a StreamingResponse so the
    sender can re-establish it while the generator drains."""
    from chirp.http.response import StreamingResponse

    async def stream_next(request):
        return StreamingResponse(chunks=iter(["<p>hi</p>"]), content_type="text/html")

    mw = CSPNonceMiddleware()
    resp = await mw(FakeRequest(), stream_next)
    assert isinstance(resp, StreamingResponse)
    assert resp.csp_nonce
    csp = _get_header(resp, "content-security-policy")
    assert f"nonce-{resp.csp_nonce}" in csp


@pytest.mark.asyncio
async def test_streaming_nonce_matches_csp_header():
    """The nonce stamped on the response equals the one in the CSP header."""
    from chirp.http.response import StreamingResponse

    async def stream_next(request):
        return StreamingResponse(chunks=iter(["x"]), content_type="text/html")

    mw = CSPNonceMiddleware()
    resp = await mw(FakeRequest(), stream_next)
    assert f"'nonce-{resp.csp_nonce}'" in _get_header(resp, "content-security-policy")


def test_set_reset_nonce_helpers_roundtrip():
    """The private set/reset helpers expose the nonce var to the sender layer."""
    from chirp.middleware.csp_nonce import _reset_csp_nonce, _set_csp_nonce

    token = _set_csp_nonce("ROUNDTRIP")
    try:
        assert get_csp_nonce() == "ROUNDTRIP"
    finally:
        _reset_csp_nonce(token)
    assert csp_nonce() == ""
