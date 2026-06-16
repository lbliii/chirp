"""E4.1-E4.2 (#325, #326) - recv buffer, stream helpers, TLS negotiation."""

import ssl

import pytest

from chirp.data.drivers._pelt import _transport
from chirp.data.drivers._pelt.errors import TLSError
from chirp.data.drivers._pelt.types import ConnectionConfig


class _ScriptedStream:
    """Minimal anyio ByteStream that replays ``responses`` on receive."""

    __slots__ = ("_responses", "_sent", "extra_attributes")

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)
        self._sent: list[bytes] = []
        self.extra_attributes = {}

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if not self._responses:
            return b""
        chunk = self._responses.pop(0)
        return chunk[:max_bytes]

    async def send(self, data: bytes) -> None:
        self._sent.append(data)

    async def aclose(self) -> None:
        return None


@pytest.mark.issue(325)
def test_recv_buffer_feed_consume_and_compact():
    buf = _transport.RecvBuffer()
    buf.feed(b"abc")
    assert bytes(buf.view()) == b"abc"
    buf.consume(2)
    assert bytes(buf.view()) == b"c"
    buf.feed(b"def")
    assert bytes(buf.view()) == b"cdef"
    huge = bytearray(65536)
    buf.feed(huge)
    buf.consume(len(huge))
    buf.compact_if_needed(slack=4096)


@pytest.mark.issue(325)
@pytest.mark.anyio
async def test_pgstream_receive_into_buffer():
    stream = _ScriptedStream([b"hello", b""])
    pg = _transport.PGStream(stream=stream)
    n = await pg.receive_into_buffer()
    assert n == 5
    assert bytes(pg.recv.view()) == b"hello"
    await pg.send(b"ack")
    assert stream._sent == [b"ack"]


@pytest.mark.issue(326)
@pytest.mark.anyio
async def test_negotiate_tls_require_accepts_ssl(monkeypatch: pytest.MonkeyPatch):
    raw = _ScriptedStream([_transport._SSL_OK])

    async def _passthrough_tls(stream: object, ctx: object) -> object:
        return stream

    monkeypatch.setattr(_transport, "_upgrade_to_tls", _passthrough_tls)
    stream = _transport.PGStream(stream=raw)
    config = ConnectionConfig(user="u", ssl="require")
    out = await _transport.negotiate_tls(stream, config)
    assert out.stream is raw
    assert raw._sent[0] == _transport._SSL_REQUEST


@pytest.mark.issue(326)
@pytest.mark.anyio
async def test_negotiate_tls_require_rejects_when_server_says_no():
    stream = _transport.PGStream(stream=_ScriptedStream([_transport._SSL_NO]))
    config = ConnectionConfig(user="u", ssl="require")
    with pytest.raises(TLSError, match="refused SSL"):
        await _transport.negotiate_tls(stream, config)


@pytest.mark.issue(326)
def test_ssl_context_verify_full_checks_hostname():
    config = ConnectionConfig(user="u", ssl="verify-full")
    ctx = _transport._ssl_context_for(config)
    assert ctx is not None
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.issue(326)
def test_ssl_context_disable_returns_none():
    config = ConnectionConfig(user="u", ssl="disable")
    assert _transport._ssl_context_for(config) is None
