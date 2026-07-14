"""anyio I/O edge for pelt: sockets, recv buffer, TLS, session handshake (epic E4).

Only this module (and later ``connection`` / ``pool`` in E5) touches anyio. The sans-I/O
``SimpleQueryProtocol`` engine is driven against a :class:`PGStream` — bytes read from the
socket are appended to a reusable :class:`RecvBuffer`, fed to :meth:`SimpleQueryProtocol.receive_bytes`,
and frontend bytes from the engine are written back. **Never hold a lock across ``await``**;
per-connection state is single-owner on one task.
"""

from __future__ import annotations

import importlib
import importlib.util
import ssl
import sys
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

import anyio
from anyio import EndOfStream
from anyio.streams.tls import TLSStream

from chirp.data.drivers._pelt import _auth
from chirp.data.drivers._pelt._protocol import (
    AuthRequestEvent,
    BackendKeyDataEvent,
    ParameterStatusEvent,
    ProtocolEvent,
    ProtocolState,
    SimpleQueryProtocol,
)
from chirp.data.drivers._pelt.errors import PeltConnectionError, PeltTimeoutError, TLSError
from chirp.data.drivers._pelt.types import ConnectionConfig

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from anyio.abc import ByteStream

_HAS_TRUSTSTORE = importlib.util.find_spec("truststore") is not None

# PostgreSQL SSLRequest payload: Int32(8) + Int32(80877103).
_SSL_REQUEST = (8).to_bytes(4, "big") + (80877103).to_bytes(4, "big")
_SSL_OK = b"S"
_SSL_NO = b"N"

# CancelRequest magic + layout (separate connection, no startup).
_CANCEL_REQUEST_CODE = 80877102


class RecvBuffer:
    """Per-connection reusable inbound buffer with zero-copy ``memoryview`` reads.

    Consumed prefix bytes are deleted immediately; when the unused tail is small but the
    allocated buffer is large, compact by copying the tail to the front (same discipline as
    the protocol engine's ``bytearray`` carry-forward).
    """

    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf = bytearray()

    def __len__(self) -> int:
        return len(self._buf)

    def feed(self, data: bytes) -> None:
        if data:
            self._buf += data

    def view(self) -> memoryview:
        return memoryview(self._buf)

    def consume(self, n: int) -> None:
        if n:
            del self._buf[:n]

    def compact_if_needed(self, *, slack: int = 4096) -> None:
        """Shrink an over-allocated buffer when the live tail is tiny."""
        if self._buf and len(self._buf) < slack and sys.getsizeof(self._buf) > slack * 8:
            self._buf = bytearray(self._buf)


@dataclass
class PGStream:
    """A bidirectional Postgres wire stream with an inbound :class:`RecvBuffer`."""

    stream: ByteStream
    recv: RecvBuffer = field(default_factory=RecvBuffer)

    async def send(self, data: bytes) -> None:
        if data:
            await self.stream.send(data)

    async def receive_into_buffer(self, max_bytes: int = 65536) -> int:
        """Read up to ``max_bytes`` from the socket into the recv buffer. Returns bytes read."""
        data = await self.stream.receive(max_bytes)
        if not data:
            return 0
        self.recv.feed(data)
        return len(data)


@dataclass(frozen=True, slots=True)
class PGSession:
    """An authenticated, ready-for-query connection session."""

    stream: PGStream
    protocol: SimpleQueryProtocol
    parameters: Mapping[str, str]
    server_version: str | None
    backend_pid: int | None
    backend_secret_key: int | None


def _is_unix_host(host: str) -> bool:
    return host.startswith("/")


def _ssl_context_for(config: ConnectionConfig) -> ssl.SSLContext | None:
    mode = config.ssl
    if mode == "disable":
        return None
    if _HAS_TRUSTSTORE:
        truststore = importlib.import_module("truststore")
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        ctx = ssl.create_default_context()
    if mode in ("verify-ca", "verify-full"):
        ctx.check_hostname = mode == "verify-full"
        ctx.verify_mode = ssl.CERT_REQUIRED
        if config.sslrootcert is not None:
            try:
                ctx.load_verify_locations(cafile=config.sslrootcert)
            except (OSError, ssl.SSLError) as exc:
                msg = f"could not load TLS CA file {config.sslrootcert!r}: {exc}"
                raise TLSError(
                    msg,
                    hint="Set sslrootcert to a readable PEM CA certificate.",
                ) from exc
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def _upgrade_to_tls(
    stream: ByteStream,
    ctx: ssl.SSLContext,
    *,
    hostname: str | None,
) -> ByteStream:
    """Wrap a connected stream in TLS (extracted for testability)."""
    tls = await TLSStream.wrap(stream, hostname=hostname, ssl_context=ctx)
    return tls


async def open_stream(config: ConnectionConfig) -> PGStream:
    """Open a TCP or Unix domain socket (no TLS yet)."""
    try:
        with anyio.fail_after(config.connect_timeout):
            if _is_unix_host(config.host):
                raw = await anyio.connect_unix(config.host)
            else:
                raw = await anyio.connect_tcp(config.host, config.port)
    except TimeoutError as exc:
        msg = f"connect timed out after {config.connect_timeout}s to {config.host}:{config.port}"
        raise PeltTimeoutError(msg) from exc
    except OSError as exc:
        msg = f"could not connect to {config.host}:{config.port}: {exc}"
        raise PeltConnectionError(msg) from exc
    return PGStream(stream=raw)


async def negotiate_tls(stream: PGStream, config: ConnectionConfig) -> PGStream:
    """Apply libpq-compatible sslmode negotiation on an already-open stream."""
    mode = config.ssl
    if mode == "disable":
        return stream

    async def _request_ssl() -> bool:
        await stream.send(_SSL_REQUEST)
        reply = await stream.stream.receive(1)
        if reply == _SSL_OK:
            return True
        if reply == _SSL_NO:
            return False
        msg = f"unexpected SSL negotiation response: {reply!r}"
        raise TLSError(msg)

    ctx = _ssl_context_for(config)
    if ctx is None:  # pragma: no cover — negotiate_tls returns early for disable
        msg = "internal error: missing SSL context for TLS negotiation"
        raise TLSError(msg)

    async def _upgrade() -> PGStream:
        hostname = None if _is_unix_host(config.host) else config.host
        try:
            tls_stream = await _upgrade_to_tls(stream.stream, ctx, hostname=hostname)
        except (ssl.SSLError, OSError, ValueError, anyio.BrokenResourceError, EndOfStream) as exc:
            msg = f"TLS handshake failed for {config.host}:{config.port} (sslmode={mode}): {exc}"
            raise TLSError(
                msg,
                hint="Verify sslmode, sslrootcert, the server certificate, and hostname.",
            ) from exc
        return PGStream(stream=tls_stream, recv=stream.recv)

    if mode == "require":
        if not await _request_ssl():
            msg = "server refused SSL connection (sslmode=require)"
            raise TLSError(msg)
        return await _upgrade()

    if mode in ("verify-ca", "verify-full"):
        if not await _request_ssl():
            msg = f"server refused SSL connection (sslmode={mode})"
            raise TLSError(msg)
        return await _upgrade()

    if mode == "allow":
        if await _request_ssl():
            return await _upgrade()
        return stream

    if mode == "prefer":
        # libpq "prefer": try non-SSL first; Postgres expects SSLRequest before startup when
        # encryption is wanted, so attempt SSL and fall back to cleartext on refusal.
        if await _request_ssl():
            return await _upgrade()
        return stream

    msg = f"unsupported sslmode: {mode!r}"
    raise TLSError(msg)


async def _drive_until_ready(
    stream: PGStream,
    protocol: SimpleQueryProtocol,
    *,
    user: str,
    password: str,
) -> PGSession:
    scram: _auth.ScramSha256Client | None = None
    parameters: dict[str, str] = {}
    server_version: str | None = None
    backend_pid: int | None = None
    backend_secret: int | None = None

    async def _handle(events: Sequence[ProtocolEvent]) -> None:
        nonlocal scram, server_version, backend_pid, backend_secret
        for event in events:
            if isinstance(event, AuthRequestEvent):
                outbound, scram = _auth.respond_to_auth(
                    event.request, user=user, password=password, scram=scram
                )
                if outbound:
                    await stream.send(outbound)
            elif isinstance(event, ParameterStatusEvent):
                parameters[event.name] = event.value
                if event.name == "server_version":
                    server_version = event.value
            elif isinstance(event, BackendKeyDataEvent):
                backend_pid = event.pid
                backend_secret = event.secret_key

    while protocol.state is not ProtocolState.READY:
        await _handle(protocol.receive_bytes(b""))
        if protocol.state is ProtocolState.READY:
            break
        try:
            chunk = await stream.stream.receive(65536)
        except EndOfStream:
            chunk = b""
        if not chunk:
            msg = "connection closed before ReadyForQuery"
            raise PeltConnectionError(msg)
        await _handle(protocol.receive_bytes(chunk))

    return PGSession(
        stream=stream,
        protocol=protocol,
        parameters=MappingProxyType(parameters),
        server_version=server_version,
        backend_pid=backend_pid,
        backend_secret_key=backend_secret,
    )


async def connect_session(config: ConnectionConfig) -> PGSession:
    """Connect, negotiate TLS, run startup + auth, and return a ready session."""
    stream = await open_stream(config)
    connected = False
    try:
        stream = await negotiate_tls(stream, config)
        protocol = SimpleQueryProtocol()
        database = config.database or config.user
        startup = protocol.send_startup(user=config.user, database=database)
        await stream.send(startup)
        session = await _drive_until_ready(
            stream,
            protocol,
            user=config.user,
            password=config.password,
        )
        connected = True
        return session
    finally:
        if not connected:
            await stream.stream.aclose()


def build_cancel_request(*, pid: int, secret_key: int) -> bytes:
    """Frontend CancelRequest (sent on a separate connection, no startup message)."""
    body = (
        (16).to_bytes(4, "big")
        + _CANCEL_REQUEST_CODE.to_bytes(4, "big")
        + pid.to_bytes(4, "big")
        + secret_key.to_bytes(4, "big")
    )
    return body


async def cancel_backend_query(
    config: ConnectionConfig,
    *,
    pid: int,
    secret_key: int,
) -> None:
    """Open a throwaway connection and send CancelRequest (best-effort)."""
    stream = await open_stream(config)
    try:
        stream = await negotiate_tls(stream, config)
        await stream.send(build_cancel_request(pid=pid, secret_key=secret_key))
    finally:
        await stream.stream.aclose()


__all__ = [
    "_HAS_TRUSTSTORE",
    "PGSession",
    "PGStream",
    "RecvBuffer",
    "build_cancel_request",
    "cancel_backend_query",
    "connect_session",
    "negotiate_tls",
    "open_stream",
]
