"""Tests for chirp.server.sender response emission rules."""

import pytest

from chirp.http.response import Response
from chirp.server.sender import send_response


class TestSendResponseNoBodyStatuses:
    @pytest.mark.asyncio
    async def test_204_drops_body_and_sets_zero_content_length(self) -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        # Even if a handler accidentally attaches body content, sender must
        # enforce RFC no-body semantics for 204.
        response = Response("unexpected-body").with_status(204)
        await send_response(response, send)

        assert messages[0]["type"] == "http.response.start"
        headers = dict(messages[0]["headers"])
        assert headers[b"content-length"] == b"0"

        assert messages[1]["type"] == "http.response.body"
        assert messages[1]["body"] == b""

    @pytest.mark.asyncio
    async def test_304_drops_body_and_sets_zero_content_length(self) -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        response = Response("unexpected-body").with_status(304)
        await send_response(response, send)

        headers = dict(messages[0]["headers"])
        assert headers[b"content-length"] == b"0"
        assert messages[1]["body"] == b""

    @pytest.mark.asyncio
    async def test_200_preserves_body(self) -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        response = Response("ok")
        await send_response(response, send)

        headers = dict(messages[0]["headers"])
        assert headers[b"content-length"] == b"2"
        assert messages[1]["body"] == b"ok"
