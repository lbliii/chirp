"""E4.1-E4.2 (#325, #326) - recv buffer, stream helpers, TLS negotiation."""

import ssl

import pytest

from chirp.data.drivers._pelt import _transport
from chirp.data.drivers._pelt.errors import TLSError
from chirp.data.drivers._pelt.types import ConnectionConfig


class _ScriptedStream:
    """Minimal anyio ByteStream that replays ``responses`` on receive."""

    __slots__ = ("_closed", "_responses", "_sent", "extra_attributes")

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)
        self._sent: list[bytes] = []
        self._closed = False
        self.extra_attributes = {}

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if not self._responses:
            return b""
        chunk = self._responses.pop(0)
        return chunk[:max_bytes]

    async def send(self, data: bytes) -> None:
        self._sent.append(data)

    async def aclose(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed


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
    seen_hostname: str | None = None

    async def _passthrough_tls(
        stream: object,
        ctx: object,
        *,
        hostname: str | None = None,
    ) -> object:
        nonlocal seen_hostname
        seen_hostname = hostname
        return stream

    monkeypatch.setattr(_transport, "_upgrade_to_tls", _passthrough_tls)
    stream = _transport.PGStream(stream=raw)
    config = ConnectionConfig(user="u", ssl="require")
    out = await _transport.negotiate_tls(stream, config)
    assert out.stream is raw
    assert raw._sent[0] == _transport._SSL_REQUEST
    assert seen_hostname == "localhost"


@pytest.mark.issue(753)
@pytest.mark.anyio
async def test_upgrade_to_tls_explicitly_uses_client_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    raw = _ScriptedStream([])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    captured: dict[str, object] = {}

    async def _capture_wrap(stream: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return stream

    monkeypatch.setattr(_transport.TLSStream, "wrap", _capture_wrap)

    out = await _transport._upgrade_to_tls(raw, context)

    assert out is raw
    assert captured == {
        "server_side": False,
        "hostname": None,
        "ssl_context": context,
    }


@pytest.mark.issue(753)
@pytest.mark.anyio
async def test_negotiate_tls_verify_full_passes_postgres_hostname(
    monkeypatch: pytest.MonkeyPatch,
):
    raw = _ScriptedStream([_transport._SSL_OK])
    captured: dict[str, object] = {}

    async def _capture_tls(
        stream: object,
        ctx: object,
        *,
        hostname: str | None = None,
    ) -> object:
        captured["hostname"] = hostname
        return stream

    monkeypatch.setattr(_transport, "_upgrade_to_tls", _capture_tls)
    stream = _transport.PGStream(stream=raw)
    config = ConnectionConfig(host="postgres.railway.internal", user="u", ssl="verify-full")

    out = await _transport.negotiate_tls(stream, config)

    assert out.stream is raw
    assert captured["hostname"] == "postgres.railway.internal"


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


@pytest.mark.issue(691)
def test_ssl_context_reports_unreadable_explicit_ca(tmp_path):
    missing = tmp_path / "missing-ca.pem"
    config = ConnectionConfig(user="u", ssl="verify-ca", sslrootcert=str(missing))

    with pytest.raises(TLSError, match="could not load TLS CA file") as caught:
        _transport._ssl_context_for(config)

    assert caught.value.code == "PELT_TLS_FAILED"
    assert caught.value.hint == "Set sslrootcert to a readable PEM CA certificate."


@pytest.mark.issue(691)
@pytest.mark.anyio
async def test_connect_session_closes_stream_when_tls_negotiation_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    raw = _ScriptedStream([_transport._SSL_NO])

    async def _open_stream(config: ConnectionConfig) -> _transport.PGStream:
        return _transport.PGStream(stream=raw)

    monkeypatch.setattr(_transport, "open_stream", _open_stream)

    with pytest.raises(TLSError, match="server refused SSL"):
        await _transport.connect_session(ConnectionConfig(user="u", ssl="require"))

    assert raw.closed is True
