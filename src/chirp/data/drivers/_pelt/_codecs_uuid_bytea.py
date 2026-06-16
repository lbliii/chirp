"""E2 codec family: ``uuid`` and ``bytea``.

Two leaf codecs that round-trip Python ``uuid.UUID`` and ``bytes`` against the PostgreSQL
binary + text wire formats. Both are *non-parametric* (a fixed OID, no element/typmod), so
they ship in :data:`LEAF_CODECS` ready for the registry — the long-tail temporal/numeric and
the parametric array/composite families land in sibling E2 modules built on the same
:class:`~chirp.data.drivers._pelt._codecs.Codec` shape.

Wire layouts (cf. ``pg_type.dat`` + ``src/backend/utils/adt/uuid.c`` / ``varlena.c``):

* ``uuid`` (OID 2950): binary is the 16 raw UUID bytes, big-endian (network) order — the same
  byte order as :attr:`uuid.UUID.bytes`. Text is the canonical 8-4-4-4-12 hyphenated hex.
* ``bytea`` (OID 17): binary is the raw octet string, a verbatim passthrough. Text is the
  PostgreSQL *hex format* — the literal prefix ``\\x`` followed by lowercase hex (the default
  ``bytea_output``); the legacy ``escape`` format is not emitted and not decoded here.

Faults raise pelt's :class:`~chirp.data.drivers._pelt.errors.ProtocolError` (a ``PELT_*``
code), never a bare exception — a malformed-length ``uuid`` or an unknown ``bytea`` text
prefix is a backend/stream defect, not programmer misuse. Live-PG parity deferred to E4/E6
integration.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from chirp.data.drivers._pelt._codecs import Codec
from chirp.data.drivers._pelt.errors import ProtocolError

# --- type OIDs (from pg_type.dat) -------------------------------------------
OID_UUID = 2950
OID_BYTEA = 17

# A binary uuid is exactly 16 octets; reject anything else as a stream defect.
_UUID_BINARY_LEN = 16


# --- codec constructors -----------------------------------------------------
def _uuid_codec() -> Codec:
    def decode_binary(data: bytes) -> _uuid.UUID:
        if len(data) != _UUID_BINARY_LEN:
            msg = f"uuid binary value must be {_UUID_BINARY_LEN} bytes, got {len(data)}"
            raise ProtocolError(
                msg, hint="the backend sent a malformed uuid; the stream may have desynced"
            )
        return _uuid.UUID(bytes=data)

    def decode_text(data: bytes) -> _uuid.UUID:
        try:
            return _uuid.UUID(data.decode("ascii"))
        except ValueError as exc:
            msg = f"uuid text value is not a valid UUID: {data!r}"
            raise ProtocolError(
                msg, hint="the backend sent a malformed uuid text representation"
            ) from exc

    def encode_binary(value: Any) -> bytes:
        return _coerce_uuid(value).bytes

    def encode_text(value: Any) -> bytes:
        return str(_coerce_uuid(value)).encode("ascii")

    return Codec(
        oid=OID_UUID,
        name="uuid",
        decode_binary=decode_binary,
        decode_text=decode_text,
        encode_binary=encode_binary,
        encode_text=encode_text,
    )


def _coerce_uuid(value: Any) -> _uuid.UUID:
    """Accept a :class:`uuid.UUID` directly, or a hyphenated/plain hex string."""
    if isinstance(value, _uuid.UUID):
        return value
    return _uuid.UUID(str(value))


def _bytea_codec() -> Codec:
    def decode_binary(data: bytes) -> bytes:
        # The wire already hands us a fresh bytes slice; return it verbatim.
        return data

    def decode_text(data: bytes) -> bytes:
        # Modern PostgreSQL (bytea_output=hex): a literal b"\\x" prefix + lowercase hex.
        if not data.startswith(b"\\x"):
            msg = f"bytea text value must use the hex (\\x...) format, got {data[:8]!r}"
            raise ProtocolError(
                msg, hint="set bytea_output=hex; the legacy escape format is not supported"
            )
        try:
            return bytes.fromhex(data[2:].decode("ascii"))
        except ValueError as exc:
            msg = f"bytea text value has invalid hex digits: {data!r}"
            raise ProtocolError(msg, hint="the backend sent a malformed bytea hex string") from exc

    def encode_binary(value: Any) -> bytes:
        return bytes(value)

    def encode_text(value: Any) -> bytes:
        return b"\\x" + bytes(value).hex().encode("ascii")

    return Codec(
        oid=OID_BYTEA,
        name="bytea",
        decode_binary=decode_binary,
        decode_text=decode_text,
        encode_binary=encode_binary,
        encode_text=encode_text,
    )


# Non-parametric codecs, ready for ``CodecRegistry.register``.
LEAF_CODECS: tuple[Codec, ...] = (_uuid_codec(), _bytea_codec())
