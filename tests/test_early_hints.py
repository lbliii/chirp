"""HTTP 103 Early Hints (RFC 8297) — Link/preload header convention.

Chirp's sender promotes asset-preload-class ``Link`` headers already on a
response to a preliminary ``103`` ``http.response.start`` frame, which pounce
0.8.0 serializes as an interim informational response over H1/H2/H3. There is
no new public API: the lever is the ``Link`` header convention.

The sender-layer tests use a raw ASGI ``send`` collector — that observes every
message including the interim 103 frame distinctly, which chirp's in-memory
``TestClient`` cannot do (it records last-wins status and discards interim
headers). The real-socket test proves the interim frame does not corrupt the
final response over an actual pounce H1 socket (httpx does not surface 1xx
frames to user code, so it can only assert the final response is intact).
"""

import httpx
import pytest

from chirp.http.response import Response, StreamingResponse
from chirp.server.sender import (
    _early_hint_headers,
    _is_early_hint_link,
    send_response,
    send_streaming_response,
)


class TestEarlyHintLinkDetection:
    @pytest.mark.parametrize(
        "value",
        [
            "</a.css>; rel=preload; as=style",
            "</a.js>; rel=modulepreload",
            "<https://cdn.example.com>; rel=preconnect",
            "<https://cdn.example.com>; rel=dns-prefetch",
            "</next>; rel=prefetch",
            # Multiple rel tokens in one header value (RFC 8288).
            '<https://cdn.example.com>; rel="preconnect dns-prefetch"',
            # Case-insensitive rel matching.
            "</a.css>; REL=Preload; as=style",
        ],
    )
    def test_eligible_links(self, value: str) -> None:
        assert _is_early_hint_link(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "</page>; rel=canonical",
            "</style.css>; rel=stylesheet",
            "<https://example.com>; rel=alternate; hreflang=en",
            "</prev>; rel=prev",
            # 'preload' as a substring of a non-rel param must not match.
            "</a.css>; rel=icon; title=preload",
        ],
    )
    def test_ineligible_links(self, value: str) -> None:
        assert _is_early_hint_link(value) is False


class TestEarlyHintCollection:
    def test_collects_only_eligible_link_headers(self) -> None:
        response = (
            Response("ok")
            .with_header("Link", "</a.css>; rel=preload; as=style")
            .with_header("Link", "</page>; rel=canonical")
            .with_header("X-Other", "ignored")
        )
        early = _early_hint_headers(response)
        assert early == [(b"link", b"</a.css>; rel=preload; as=style")]

    def test_empty_when_no_eligible_links(self) -> None:
        response = Response("ok").with_header("Link", "</page>; rel=canonical")
        assert _early_hint_headers(response) == []


class TestSendResponseEarlyHints:
    @pytest.mark.asyncio
    async def test_emits_103_before_final_start(self) -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        response = Response("<html>...</html>").with_header(
            "Link", "</static/app.css>; rel=preload; as=style"
        )
        await send_response(response, send)

        # Interim 103 frame is emitted FIRST, carrying the Link header and no body.
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 103
        assert messages[0]["headers"] == [(b"link", b"</static/app.css>; rel=preload; as=style")]

        # Final start frame follows, unaffected.
        assert messages[1]["type"] == "http.response.start"
        assert messages[1]["status"] == 200

        # The canonical Link header remains on the FINAL response too (RFC 8297:
        # the 103 hint is advisory; the Link header still belongs on the final
        # message).
        final_headers = messages[1]["headers"]
        assert (b"link", b"</static/app.css>; rel=preload; as=style") in final_headers

        # Body is on the final response only.
        assert messages[2]["type"] == "http.response.body"
        assert messages[2]["body"] == b"<html>...</html>"

    @pytest.mark.asyncio
    async def test_no_103_without_eligible_link(self) -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        # A non-preload Link header must NOT trigger an interim frame.
        response = Response("ok").with_header("Link", "</page>; rel=canonical")
        await send_response(response, send)

        assert all(m.get("status") != 103 for m in messages)
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_no_103_without_link_header(self) -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        await send_response(Response("ok"), send)

        assert messages[0]["status"] == 200
        assert all(m.get("status") != 103 for m in messages)


class TestSendStreamingResponseEarlyHints:
    @pytest.mark.asyncio
    async def test_streaming_emits_103_before_final_start(self) -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        def chunks():
            yield "<html>"
            yield "</html>"

        response = StreamingResponse(
            chunks=chunks(),
            headers=(("Link", "</static/app.css>; rel=preload; as=style"),),
        )
        await send_streaming_response(response, send)

        assert messages[0]["status"] == 103
        assert messages[0]["headers"] == [(b"link", b"</static/app.css>; rel=preload; as=style")]
        # Final streaming start follows the interim frame.
        assert messages[1]["type"] == "http.response.start"
        assert messages[1]["status"] == 200
        assert (b"transfer-encoding", b"chunked") in messages[1]["headers"]


class TestEarlyHintsRealSocket:
    """End-to-end over a real pounce H1 socket.

    httpx does not expose interim 1xx frames to user code, so this only proves
    the interim 103 frame does not corrupt the final response (regression guard
    that emitting two ``http.response.start`` messages is safe over the wire).
    The distinct 103 assertions live in the sender-layer tests above.
    """

    @pytest.mark.asyncio
    async def test_final_response_intact_with_early_hints(self) -> None:
        pytest.importorskip("pounce.testing")
        from pounce.testing import serve

        async def app(scope, receive, send) -> None:
            assert scope["type"] == "http"
            response = Response("<html>hello</html>").with_header(
                "Link", "</static/app.css>; rel=preload; as=style"
            )
            await send_response(response, send)

        async with serve(app) as server, httpx.AsyncClient() as client:
            resp = await client.get(server.url)

        assert resp.status_code == 200
        assert resp.text == "<html>hello</html>"
        # Link header survives on the final response.
        assert resp.headers["link"] == "</static/app.css>; rel=preload; as=style"
