"""Signed skill result envelope — provenance you can verify but not forge.

``Envelope`` is a frozen return type: handlers (and later ``skill.tool``) return
it, ``negotiate()`` serializes the wire dict as JSON, and callers verify the
Ed25519 signature over all metadata fields.

``alg`` is reserved for a future HMAC mode; only ``Ed25519`` is accepted now.
"""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import dataclass
from typing import Any

_ALG_ED25519 = "Ed25519"
_CRYPTO_INSTALL_ERROR = (
    "Envelope Ed25519 sign/verify requires the 'cryptography' package. "
    "Install it with: pip install 'chirp[skill]'"
)


@dataclass(frozen=True, slots=True)
class Envelope:
    """Signed skill-tool result with verifiable provenance metadata."""

    payload: Any
    skill: str
    version: str
    tool: str
    nonce: str
    input_digest: str
    signature: str
    key_id: str
    alg: str = _ALG_ED25519

    def to_wire(self) -> dict[str, Any]:
        """Return the JSON-serializable wire dict for ``negotiate()``."""
        return {
            "payload": self.payload,
            "skill": self.skill,
            "version": self.version,
            "tool": self.tool,
            "nonce": self.nonce,
            "input_digest": self.input_digest,
            "signature": self.signature,
            "key_id": self.key_id,
            "alg": self.alg,
        }


def _canonical_bytes(fields: dict[str, Any]) -> bytes:
    """Deterministic UTF-8 JSON used as the Ed25519 message."""
    return json.dumps(
        fields,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _signed_fields(
    *,
    payload: Any,
    skill: str,
    version: str,
    tool: str,
    nonce: str,
    input_digest: str,
    key_id: str,
    alg: str,
) -> dict[str, Any]:
    return {
        "payload": payload,
        "skill": skill,
        "version": version,
        "tool": tool,
        "nonce": nonce,
        "input_digest": input_digest,
        "key_id": key_id,
        "alg": alg,
    }


def _require_cryptography() -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise ImportError(_CRYPTO_INSTALL_ERROR) from exc
    return ed25519


def _load_private_key(private_key: Any) -> Any:
    ed25519 = _require_cryptography()
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return private_key
    if isinstance(private_key, bytes | bytearray):
        return ed25519.Ed25519PrivateKey.from_private_bytes(bytes(private_key))
    msg = "private_key must be Ed25519PrivateKey or 32 raw private-key bytes"
    raise TypeError(msg)


def _load_public_key(public_key: Any) -> Any:
    ed25519 = _require_cryptography()
    if isinstance(public_key, ed25519.Ed25519PublicKey):
        return public_key
    if isinstance(public_key, bytes | bytearray):
        return ed25519.Ed25519PublicKey.from_public_bytes(bytes(public_key))
    msg = "public_key must be Ed25519PublicKey or 32 raw public-key bytes"
    raise TypeError(msg)


def sign_envelope(
    *,
    payload: Any,
    skill: str,
    version: str,
    tool: str,
    input_digest: str,
    private_key: Any,
    key_id: str,
    nonce: str | None = None,
    alg: str = _ALG_ED25519,
) -> Envelope:
    """Build a signed ``Envelope`` covering all metadata fields.

    ``nonce`` defaults to a fresh url-safe token. ``alg`` must be ``Ed25519``
    until HMAC mode lands; the field is retained for that later mode.
    """
    if alg != _ALG_ED25519:
        msg = f"Unsupported envelope alg {alg!r}; only {_ALG_ED25519!r} is implemented"
        raise ValueError(msg)

    resolved_nonce = nonce if nonce is not None else secrets.token_urlsafe(16)
    fields = _signed_fields(
        payload=payload,
        skill=skill,
        version=version,
        tool=tool,
        nonce=resolved_nonce,
        input_digest=input_digest,
        key_id=key_id,
        alg=alg,
    )
    key = _load_private_key(private_key)
    signature = base64.b64encode(key.sign(_canonical_bytes(fields))).decode("ascii")
    return Envelope(
        payload=payload,
        skill=skill,
        version=version,
        tool=tool,
        nonce=resolved_nonce,
        input_digest=input_digest,
        signature=signature,
        key_id=key_id,
        alg=alg,
    )


def verify_envelope(env: Envelope, public_key: Any) -> bool:
    """Return ``True`` when ``env``'s Ed25519 signature matches ``public_key``.

    Tampered metadata or payload, wrong key, or unsupported ``alg`` yields
    ``False``. Malformed base64 signatures also fail closed.
    """
    if env.alg != _ALG_ED25519:
        return False
    try:
        signature = base64.b64decode(env.signature.encode("ascii"), validate=True)
    except ValueError, UnicodeEncodeError:
        return False

    fields = _signed_fields(
        payload=env.payload,
        skill=env.skill,
        version=env.version,
        tool=env.tool,
        nonce=env.nonce,
        input_digest=env.input_digest,
        key_id=env.key_id,
        alg=env.alg,
    )
    key = _load_public_key(public_key)
    try:
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ImportError(_CRYPTO_INSTALL_ERROR) from exc
    try:
        key.verify(signature, _canonical_bytes(fields))
    except InvalidSignature:
        return False
    return True


__all__ = [
    "Envelope",
    "sign_envelope",
    "verify_envelope",
]
