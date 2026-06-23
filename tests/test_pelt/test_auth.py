"""E4.3 (#327) — SCRAM-SHA-256, MD5, and cleartext auth responders."""

import base64
import hashlib
import hmac

import pytest

from chirp.data.drivers._pelt import _auth
from chirp.data.drivers._pelt._messages import (
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
)
from chirp.data.drivers._pelt.errors import AuthenticationError


def _server_final_for(client: _auth.ScramSha256Client) -> bytes:
    """Build a valid server-final verifier from the client's post-continue state."""
    server_key = hmac.new(client._salted_password, b"Server Key", hashlib.sha256).digest()
    verifier = hmac.new(server_key, client._auth_message.encode("ascii"), hashlib.sha256).digest()
    return b"v=" + base64.b64encode(verifier)


@pytest.mark.issue(327)
def test_scram_client_first_uses_sasl_password_frame():
    client = _auth.ScramSha256Client(user="chirp", password="chirp")
    msg = client.client_first_message()
    # mechanism cstring + Int32 length + SCRAM payload (not a bare NUL-terminated password)
    assert msg.startswith(b"p")
    body = msg[5:]
    assert body.startswith(b"SCRAM-SHA-256\x00")
    length = int.from_bytes(body[14:18], "big")
    assert length > 0
    assert body[18:].startswith(b"n,,")


@pytest.mark.issue(327)
def test_scram_sha256_proof_and_verifier_roundtrip():
    user = "user"
    password = "pencil"
    client = _auth.ScramSha256Client(
        user=user,
        password=password,
        _client_nonce="rOprNGfw6EPPo2XYbHnJMWxKrI9n1lN3AKClTf8",
    )
    first = client.client_first_message()
    assert first.startswith(b"p")
    server_first = (
        b"r=rOprNGfw6EPPo2XYbHnJMWxKrI9n1lN3AKClTf8YWPiMIZENitwcs,s=QSXCR+Q6sek8bf92,i=4096"
    )
    final = client.client_final_message(server_first)
    assert b",p=" in final
    client.verify_server_final(_server_final_for(client))


@pytest.mark.issue(327)
def test_scram_rejects_unsupported_mechanism():
    with pytest.raises(AuthenticationError, match="no supported SASL"):
        _auth.respond_to_auth(AuthenticationSASL(mechanisms=("PLAIN",)), user="u", password="p")


@pytest.mark.issue(328)
def test_md5_password_vector():
    user = "postgres"
    password = "secret"
    salt = bytes.fromhex("01234567")
    expected_inner = hashlib.md5((password + user).encode()).hexdigest().encode("ascii")  # noqa: S324
    expected = hashlib.md5(expected_inner + salt).hexdigest()  # noqa: S324
    msg = _auth.build_md5_password(user=user, password=password, salt=salt)
    assert expected.encode("ascii") in msg


@pytest.mark.issue(328)
def test_cleartext_password():
    msg = _auth.build_cleartext_password("s3cret")
    assert msg.endswith(b"s3cret\x00")


@pytest.mark.issue(327)
def test_scram_continue_without_client_raises():
    with pytest.raises(AuthenticationError, match="without an in-flight"):
        _auth.respond_to_auth(
            AuthenticationSASLContinue(data=b"r=x,s=e,i=1"),
            user="u",
            password="p",
        )


@pytest.mark.issue(327)
def test_scram_full_respond_to_auth_roundtrip():
    user = "user"
    password = "pencil"
    outbound, scram = _auth.respond_to_auth(
        AuthenticationSASL(mechanisms=("SCRAM-SHA-256",)),
        user=user,
        password=password,
    )
    assert outbound
    assert scram is not None
    server_first = f"r={scram._client_nonce}suffix,s=QSXCR+Q6sek8bf92,i=4096".encode()
    outbound2, scram = _auth.respond_to_auth(
        AuthenticationSASLContinue(data=server_first),
        user=user,
        password=password,
        scram=scram,
    )
    assert outbound2
    assert scram is not None
    outbound3, _ = _auth.respond_to_auth(
        AuthenticationSASLFinal(data=_server_final_for(scram)),
        user=user,
        password=password,
        scram=scram,
    )
    assert outbound3 == b""
