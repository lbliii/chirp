"""E4.5 (#329) — scripted handshake against a fake backend byte stream."""

import pytest

from chirp.data.drivers._pelt import _transport
from chirp.data.drivers._pelt.types import ConnectionConfig
from tests.test_pelt.test_transport import _ScriptedStream


def _frame(tag: bytes, payload: bytes) -> bytes:
    return tag + (len(payload) + 4).to_bytes(4, "big") + payload


def _auth_ok() -> bytes:
    return _frame(b"R", (0).to_bytes(4, "big"))


def _cleartext_request() -> bytes:
    return _frame(b"R", (3).to_bytes(4, "big"))


def _parameter_status(name: str, value: str) -> bytes:
    return _frame(b"S", name.encode() + b"\x00" + value.encode() + b"\x00")


def _backend_key(pid: int, secret: int) -> bytes:
    return _frame(b"K", pid.to_bytes(4, "big") + secret.to_bytes(4, "big"))


def _ready() -> bytes:
    return _frame(b"Z", b"I")


@pytest.mark.issue(329)
@pytest.mark.anyio
async def test_connect_session_cleartext_handshake():
    backend = b"".join(
        [
            _cleartext_request(),
            _auth_ok(),
            _parameter_status("server_version", "16.0"),
            _backend_key(42, 999),
            _ready(),
        ]
    )
    stream = _ScriptedStream([backend])
    pg = _transport.PGStream(stream=stream)
    config = ConnectionConfig(user="alice", password="secret", database="app", ssl="disable")
    protocol = __import__(
        "chirp.data.drivers._pelt._protocol", fromlist=["SimpleQueryProtocol"]
    ).SimpleQueryProtocol()
    startup = protocol.send_startup(user=config.user, database=config.database)
    await pg.send(startup)
    session = await _transport._drive_until_ready(
        pg, protocol, user=config.user, password=config.password
    )
    assert session.server_version == "16.0"
    assert session.backend_pid == 42
    assert session.backend_secret_key == 999
    assert session.protocol.state.name == "READY"
    assert stream._sent[0] == startup
    assert b"secret" in stream._sent[1]


@pytest.mark.issue(330)
def test_build_cancel_request_layout():
    payload = _transport.build_cancel_request(pid=123, secret_key=456)
    assert len(payload) == 16
    assert int.from_bytes(payload[4:8], "big") == 80877102
    assert int.from_bytes(payload[8:12], "big") == 123
    assert int.from_bytes(payload[12:16], "big") == 456
