"""Skill packaging manifest — identity metadata for a mounted skill.

``Manifest`` is assembled from a skill's name, semver, tool list, public key,
provider-key *names* (not secrets), and a content digest. At ``app.freeze()``
the digest is finalized over tool schemas + template sources + public key and
the manifest is immutable thereafter.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Manifest:
    """Serializable skill identity record."""

    name: str
    version: str
    tools: tuple[str, ...]
    public_key: str
    provider_keys: tuple[str, ...]
    content_digest: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (round-trips via :meth:`from_dict`)."""
        return {
            "name": self.name,
            "version": self.version,
            "tools": list(self.tools),
            "public_key": self.public_key,
            "provider_keys": list(self.provider_keys),
            "content_digest": self.content_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Reconstruct a :class:`Manifest` from :meth:`to_dict` output."""
        return cls(
            name=str(data["name"]),
            version=str(data["version"]),
            tools=tuple(str(t) for t in data["tools"]),
            public_key=str(data["public_key"]),
            provider_keys=tuple(str(k) for k in data["provider_keys"]),
            content_digest=str(data["content_digest"]),
        )


def encode_public_key(public_key: Any) -> str:
    """Encode an Ed25519 public key as url-safe base64 (no padding)."""
    raw = _public_key_bytes(public_key)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def compute_content_digest(
    *,
    tool_schemas: Mapping[str, Mapping[str, Any]],
    template_sources: Mapping[str, str],
    public_key: str,
) -> str:
    """SHA-256 digest over tool schemas + template sources + public key.

    Canonical JSON (sorted keys, compact separators) so identical inputs yield
    a stable ``sha256:...`` digest across freezes.
    """
    payload = {
        "public_key": public_key,
        "templates": {name: template_sources[name] for name in sorted(template_sources)},
        "tools": {name: dict(tool_schemas[name]) for name in sorted(tool_schemas)},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assemble_manifest(
    *,
    name: str,
    version: str,
    tools: tuple[str, ...],
    public_key: Any,
    provider_keys: tuple[str, ...] = (),
    content_digest: str | None = None,
    tool_schemas: Mapping[str, Mapping[str, Any]] | None = None,
    template_sources: Mapping[str, str] | None = None,
) -> Manifest:
    """Build a :class:`Manifest`.

    When ``content_digest`` is omitted, a digest is computed from
    ``tool_schemas`` + ``template_sources`` + the encoded public key when
    schemas are provided; otherwise a provisional identity digest is used
    (pre-freeze convenience — freeze replaces it via :func:`compute_content_digest`).
    """
    encoded_key = encode_public_key(public_key)
    ordered_tools = tuple(tools)
    ordered_providers = tuple(provider_keys)
    if content_digest is not None:
        digest = content_digest
    elif tool_schemas is not None:
        digest = compute_content_digest(
            tool_schemas=tool_schemas,
            template_sources=template_sources or {},
            public_key=encoded_key,
        )
    else:
        digest = _provisional_digest(
            name=name,
            version=version,
            tools=ordered_tools,
            public_key=encoded_key,
            provider_keys=ordered_providers,
        )
    return Manifest(
        name=name,
        version=version,
        tools=ordered_tools,
        public_key=encoded_key,
        provider_keys=ordered_providers,
        content_digest=digest,
    )


def _provisional_digest(
    *,
    name: str,
    version: str,
    tools: tuple[str, ...],
    public_key: str,
    provider_keys: tuple[str, ...],
) -> str:
    """SHA-256 over canonical identity fields (pre-freeze only)."""
    payload = {
        "name": name,
        "version": version,
        "tools": list(tools),
        "public_key": public_key,
        "provider_keys": list(provider_keys),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _public_key_bytes(public_key: Any) -> bytes:
    if isinstance(public_key, bytes | bytearray):
        return bytes(public_key)
    # Lazy: avoid importing cryptography at module import time (milo pattern).
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ImportError(
            "Manifest public-key encoding requires the 'cryptography' package. "
            "Install it with: pip install 'chirp[skill]'"
        ) from exc
    if isinstance(public_key, Ed25519PublicKey):
        return public_key.public_bytes_raw()
    msg = "public_key must be Ed25519PublicKey or 32 raw public-key bytes"
    raise TypeError(msg)


__all__ = [
    "Manifest",
    "assemble_manifest",
    "compute_content_digest",
    "encode_public_key",
]
