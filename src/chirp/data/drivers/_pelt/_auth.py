"""PostgreSQL authentication helpers for the pelt I/O edge (epic E4).

Pure functions and small state machines that turn backend auth challenges into frontend
``PasswordMessage`` bytes via :func:`._builder.build_password`. SCRAM-SHA-256 uses only
stdlib ``hashlib`` / ``hmac`` / ``secrets`` — no channel binding (asyncpg parity; anyio
lacks ``server-end-point``). MD5 and cleartext cover legacy/dev servers.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from chirp.data.drivers._pelt import _builder
from chirp.data.drivers._pelt._messages import (
    AuthenticationCleartextPassword,
    AuthenticationMD5Password,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
)
from chirp.data.drivers._pelt._protocol import AuthRequest
from chirp.data.drivers._pelt.errors import AuthenticationError

_SCRAM_SHA256 = "SCRAM-SHA-256"
_CLIENT_KEY = b"Client Key"
_SERVER_KEY = b"Server Key"


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def _hi(password: bytes, salt: bytes, iterations: int) -> bytes:
    """SCRAM ``Hi()`` — PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password, salt, iterations)


def _parse_server_first(data: bytes) -> tuple[str, bytes, int]:
    """Parse ``r=...,s=...,i=...`` from a server-first message."""
    text = data.decode("utf-8")
    parts: dict[str, str] = {}
    for item in text.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key] = value
    nonce = parts.get("r")
    salt_b64 = parts.get("s")
    iteration_text = parts.get("i")
    if not nonce or not salt_b64 or not iteration_text:
        msg = f"malformed SCRAM server-first message: {text!r}"
        raise AuthenticationError(msg)
    try:
        iterations = int(iteration_text)
    except ValueError as exc:
        msg = f"invalid SCRAM iteration count: {iteration_text!r}"
        raise AuthenticationError(msg) from exc
    if iterations <= 0:
        msg = f"SCRAM iteration count must be > 0 (got {iterations})"
        raise AuthenticationError(msg)
    try:
        salt = base64.b64decode(salt_b64)
    except (ValueError, binascii.Error) as exc:
        msg = f"invalid SCRAM salt encoding: {salt_b64!r}"
        raise AuthenticationError(msg) from exc
    return nonce, salt, iterations


def _parse_server_final(data: bytes) -> str:
    text = data.decode("utf-8")
    for item in text.split(","):
        if item.startswith("v="):
            return item[2:]
    msg = f"malformed SCRAM server-final message: {text!r}"
    raise AuthenticationError(msg)


@dataclass
class ScramSha256Client:
    """Incremental SCRAM-SHA-256 client exchange (no channel binding)."""

    user: str
    password: str
    _client_nonce: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    _client_first_bare: str = field(init=False, default="")
    _server_first: str = field(init=False, default="")
    _salted_password: bytes = field(init=False, default=b"")
    _auth_message: str = field(init=False, default="")

    def __post_init__(self) -> None:
        if not self.user:
            msg = "SCRAM requires a non-empty user"
            raise AuthenticationError(msg)
        self._client_first_bare = f"n={_escape_name(self.user)},r={self._client_nonce}"

    def client_first_message(self) -> bytes:
        """First SASL payload after ``AuthenticationSASL``."""
        payload = f"n,,{self._client_first_bare}".encode()
        return _builder.build_password(payload)

    def client_final_message(self, server_first: bytes) -> bytes:
        """Reply to ``AuthenticationSASLContinue``."""
        nonce, salt, iterations = _parse_server_first(server_first)
        if not nonce.startswith(self._client_nonce):
            msg = "SCRAM server nonce does not extend the client nonce"
            raise AuthenticationError(msg)
        self._server_first = server_first.decode("utf-8")
        password_bytes = self.password.encode("utf-8")
        self._salted_password = _hi(password_bytes, salt, iterations)
        client_key = _hmac_sha256(self._salted_password, _CLIENT_KEY)
        stored_key = hashlib.sha256(client_key).digest()
        client_final_without_proof = f"c=biws,r={nonce}"
        self._auth_message = (
            (f"{self._client_first_bare},{self._server_first},{client_final_without_proof}")
            .encode()
            .decode("ascii")
        )
        client_signature = _hmac_sha256(stored_key, self._auth_message.encode("ascii"))
        proof = bytes(a ^ b for a, b in zip(client_key, client_signature, strict=True))
        proof_b64 = base64.b64encode(proof).decode("ascii")
        payload = f"{client_final_without_proof},p={proof_b64}".encode()
        return _builder.build_password(payload)

    def verify_server_final(self, server_final: bytes) -> None:
        """Validate the server signature in ``AuthenticationSASLFinal``."""
        verifier_b64 = _parse_server_final(server_final)
        try:
            verifier = base64.b64decode(verifier_b64)
        except (ValueError, binascii.Error) as exc:
            msg = f"invalid SCRAM server verifier encoding: {verifier_b64!r}"
            raise AuthenticationError(msg) from exc
        server_key = _hmac_sha256(self._salted_password, _SERVER_KEY)
        expected = _hmac_sha256(server_key, self._auth_message.encode("ascii"))
        if not hmac.compare_digest(verifier, expected):
            msg = "SCRAM server authentication failed (verifier mismatch)"
            raise AuthenticationError(msg)


def _escape_name(name: str) -> str:
    return name.replace("=", "=3D").replace(",", "=2C")


def build_cleartext_password(password: str) -> bytes:
    """Respond to ``AuthenticationCleartextPassword``."""
    return _builder.build_password(password.encode("utf-8"))


def build_md5_password(*, user: str, password: str, salt: bytes) -> bytes:
    """Respond to ``AuthenticationMD5Password``."""
    if len(salt) != 4:
        msg = f"MD5 auth salt must be 4 bytes (got {len(salt)})"
        raise AuthenticationError(msg)
    inner = hashlib.md5((password + user).encode()).hexdigest().encode("ascii")  # noqa: S324
    digest = hashlib.md5(inner + salt).hexdigest()  # noqa: S324
    return _builder.build_password(f"md5{digest}".encode("ascii"))


def respond_to_auth(
    request: AuthRequest,
    *,
    user: str,
    password: str,
    scram: ScramSha256Client | None = None,
) -> tuple[bytes, ScramSha256Client | None]:
    """Build the frontend bytes for one auth challenge.

    Returns ``(password_message_bytes, updated_scram_client)``. ``scram`` must be reused
    across the SASL continue/final rounds on the same connection.
    """
    if isinstance(request, AuthenticationCleartextPassword):
        return build_cleartext_password(password), scram
    if isinstance(request, AuthenticationMD5Password):
        return build_md5_password(user=user, password=password, salt=request.salt), scram
    if isinstance(request, AuthenticationSASL):
        if _SCRAM_SHA256 not in request.mechanisms:
            offered = ", ".join(request.mechanisms) or "(none)"
            msg = f"server offered no supported SASL mechanism (got {offered})"
            raise AuthenticationError(msg)
        client = ScramSha256Client(user=user, password=password)
        return client.client_first_message(), client
    if isinstance(request, AuthenticationSASLContinue):
        if scram is None:
            msg = "SCRAM continue received without an in-flight SCRAM client"
            raise AuthenticationError(msg)
        return scram.client_final_message(request.data), scram
    if isinstance(request, AuthenticationSASLFinal):
        if scram is None:
            msg = "SCRAM final received without an in-flight SCRAM client"
            raise AuthenticationError(msg)
        scram.verify_server_final(request.data)
        return b"", scram
    msg = f"unsupported auth request: {type(request).__name__}"
    raise AuthenticationError(msg)
