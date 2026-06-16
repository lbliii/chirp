"""E2 codec family: ``json`` / ``jsonb``.

PostgreSQL's two document types decode to a parsed Python object (whatever
:func:`json.loads` yields — ``dict`` / ``list`` / ``str`` / ``int`` / ``float`` / ``bool`` /
``None``) and encode from one via :func:`json.dumps`. The two differ only in their *binary*
wire framing:

* ``json`` (OID 114) stores the document verbatim, so its binary format is identical to its
  text format: UTF-8 JSON bytes, no envelope.
* ``jsonb`` (OID 3802) prefixes the UTF-8 JSON with a single **version byte**. Version ``1``
  is the only one PostgreSQL has ever emitted (``jsonb_send`` writes ``0x01`` then the
  decompressed text; ``jsonb_recv`` reads the version then the text). A byte other than
  ``0x01`` means the stream desynced or the server speaks a future format pelt does not
  know — that is a :class:`ProtocolError`, never a silent best-effort decode.

These are leaf (non-parametric) codecs — the registry registers them directly from
:data:`LEAF_CODECS`. Composite/array families that *contain* json land separately in E2.
Live-PG parity is deferred to E4/E6 integration; the binary vectors here are pinned to the
documented ``jsonb`` wire layout.
"""

from __future__ import annotations

import json
from typing import Any

from chirp.data.drivers._pelt._codecs import Codec
from chirp.data.drivers._pelt.errors import ProtocolError

# --- type OIDs (from pg_type.dat) -------------------------------------------
OID_JSON = 114
OID_JSONB = 3802

# The only jsonb binary version PostgreSQL emits; see jsonb_send/jsonb_recv.
_JSONB_VERSION = 1
_JSONB_VERSION_BYTE = b"\x01"


def _dumps(value: Any) -> bytes:
    """Serialize a Python object to compact UTF-8 JSON bytes.

    Compact == no whitespace between tokens (``separators=(",", ":")``). PostgreSQL parses
    json/jsonb regardless of internal whitespace, so dropping the spaces is wire-safe and
    shrinks the payload.
    """
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _loads(data: bytes) -> Any:
    """Parse UTF-8 JSON bytes to a Python object, surfacing faults as :class:`ProtocolError`."""
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"invalid JSON payload: {exc}"
        raise ProtocolError(msg) from exc


def _json_codec() -> Codec:
    """``json`` (OID 114): binary == text == UTF-8 JSON, no envelope."""

    def decode(data: bytes) -> Any:
        return _loads(data)

    def encode(value: Any) -> bytes:
        return _dumps(value)

    return Codec(
        oid=OID_JSON,
        name="json",
        decode_binary=decode,
        decode_text=decode,
        encode_binary=encode,
        encode_text=encode,
    )


def _jsonb_codec() -> Codec:
    """``jsonb`` (OID 3802): binary is ``0x01`` + UTF-8 JSON; text is bare UTF-8 JSON."""

    def decode_binary(data: bytes) -> Any:
        if not data:
            msg = "empty jsonb payload: expected a leading version byte"
            raise ProtocolError(msg)
        version = data[0]
        if version != _JSONB_VERSION:
            msg = f"unsupported jsonb version byte 0x{version:02x} (only 0x01 is known)"
            raise ProtocolError(msg)
        return _loads(data[1:])

    def decode_text(data: bytes) -> Any:
        return _loads(data)

    def encode_binary(value: Any) -> bytes:
        return _JSONB_VERSION_BYTE + _dumps(value)

    def encode_text(value: Any) -> bytes:
        return _dumps(value)

    return Codec(
        oid=OID_JSONB,
        name="jsonb",
        decode_binary=decode_binary,
        decode_text=decode_text,
        encode_binary=encode_binary,
        encode_text=encode_text,
    )


# Non-parametric codecs ready for the registry to register uniformly.
LEAF_CODECS: tuple[Codec, ...] = (_json_codec(), _jsonb_codec())
