"""Type codecs and the OID→codec registry.

A :class:`Codec` knows how to encode a Python value to wire bytes and decode wire bytes back,
in both binary and text formats. The :class:`CodecRegistry` maps PostgreSQL type OIDs to
codecs; it is the one genuinely shared-mutable structure in the hot path, so it is
``threading.Lock``-guarded, exposes reads as a :class:`types.MappingProxyType` snapshot, and
**fails loud** on a conflicting re-registration (never last-wins) — the chirp ``shapes``
registry discipline.

The E1 spine ships only the hottest OIDs (ints, text, bool, floats). The long tail (numeric,
temporal, json/jsonb, arrays, composites) lands in epic E2, and per-row decode parallelism
across free-threaded workers lands in epic E6 — both built on the immutable snapshot this
registry hands out.
"""

from __future__ import annotations

import struct
import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

# --- common type OIDs (from pg_type.dat) ------------------------------------
OID_BOOL = 16
OID_INT8 = 20
OID_INT2 = 21
OID_INT4 = 23
OID_TEXT = 25
OID_FLOAT4 = 700
OID_FLOAT8 = 701
OID_BPCHAR = 1042
OID_VARCHAR = 1043

_PACK_FLOAT4 = struct.Struct(">f")
_PACK_FLOAT8 = struct.Struct(">d")


@dataclass(frozen=True, slots=True, kw_only=True)
class Codec:
    """An immutable encode/decode pair for one PostgreSQL type.

    ``decode_*`` take the raw column bytes; ``encode_*`` return the raw column bytes.
    ``prefers_binary`` selects the wire format the driver requests when it controls the choice.
    """

    oid: int
    name: str
    decode_binary: Callable[[bytes], Any]
    decode_text: Callable[[bytes], Any]
    encode_binary: Callable[[Any], bytes]
    encode_text: Callable[[Any], bytes]
    prefers_binary: bool = True


class CodecRegistry:
    """A lock-guarded OID→:class:`Codec` map that hands out immutable snapshots."""

    __slots__ = ("_by_oid", "_lock")

    def __init__(self) -> None:
        self._by_oid: dict[int, Codec] = {}
        self._lock = threading.Lock()

    def register(self, codec: Codec) -> None:
        """Register ``codec`` for its OID. Re-registering the *same* codec is a no-op;
        registering a *different* codec for an occupied OID raises :class:`ValueError`."""
        with self._lock:
            existing = self._by_oid.get(codec.oid)
            if existing is not None and existing != codec:
                msg = (
                    f"conflicting codec for OID {codec.oid}: "
                    f"{existing.name!r} already registered, refusing to replace with {codec.name!r}"
                )
                raise ValueError(msg)
            self._by_oid[codec.oid] = codec

    def get(self, oid: int) -> Codec | None:
        with self._lock:
            return self._by_oid.get(oid)

    def snapshot(self) -> Mapping[int, Codec]:
        """An immutable point-in-time view. Hot loops resolve against this (copy-on-write),
        never under the lock per row."""
        with self._lock:
            return MappingProxyType(dict(self._by_oid))


# --- codec constructors -----------------------------------------------------
def _int_codec(oid: int, name: str, size: int) -> Codec:
    def decode_binary(data: bytes) -> int:
        return int.from_bytes(data, "big", signed=True)

    def decode_text(data: bytes) -> int:
        return int(data.decode("ascii"))

    def encode_binary(value: Any) -> bytes:
        return int(value).to_bytes(size, "big", signed=True)

    def encode_text(value: Any) -> bytes:
        return str(int(value)).encode("ascii")

    return Codec(
        oid=oid,
        name=name,
        decode_binary=decode_binary,
        decode_text=decode_text,
        encode_binary=encode_binary,
        encode_text=encode_text,
    )


def _float_codec(oid: int, name: str, packer: struct.Struct) -> Codec:
    def decode_binary(data: bytes) -> float:
        return packer.unpack(data)[0]

    def decode_text(data: bytes) -> float:
        return float(data.decode("ascii"))

    def encode_binary(value: Any) -> bytes:
        return packer.pack(float(value))

    def encode_text(value: Any) -> bytes:
        return repr(float(value)).encode("ascii")

    return Codec(
        oid=oid,
        name=name,
        decode_binary=decode_binary,
        decode_text=decode_text,
        encode_binary=encode_binary,
        encode_text=encode_text,
    )


def _text_codec(oid: int, name: str) -> Codec:
    def decode(data: bytes) -> str:
        return data.decode("utf-8")

    def encode(value: Any) -> bytes:
        return str(value).encode("utf-8")

    return Codec(
        oid=oid,
        name=name,
        decode_binary=decode,
        decode_text=decode,
        encode_binary=encode,
        encode_text=encode,
        prefers_binary=False,
    )


def _bool_codec() -> Codec:
    def decode_binary(data: bytes) -> bool:
        return data != b"\x00"

    def decode_text(data: bytes) -> bool:
        return data == b"t"

    def encode_binary(value: Any) -> bytes:
        return b"\x01" if value else b"\x00"

    def encode_text(value: Any) -> bytes:
        return b"t" if value else b"f"

    return Codec(
        oid=OID_BOOL,
        name="bool",
        decode_binary=decode_binary,
        decode_text=decode_text,
        encode_binary=encode_binary,
        encode_text=encode_text,
    )


def _builtin_codecs() -> tuple[Codec, ...]:
    return (
        _int_codec(OID_INT2, "int2", 2),
        _int_codec(OID_INT4, "int4", 4),
        _int_codec(OID_INT8, "int8", 8),
        _float_codec(OID_FLOAT4, "float4", _PACK_FLOAT4),
        _float_codec(OID_FLOAT8, "float8", _PACK_FLOAT8),
        _bool_codec(),
        _text_codec(OID_TEXT, "text"),
        _text_codec(OID_VARCHAR, "varchar"),
        _text_codec(OID_BPCHAR, "bpchar"),
    )


def build_default_registry() -> CodecRegistry:
    """A fresh registry pre-loaded with the E1 hot-path codecs."""
    registry = CodecRegistry()
    for codec in _builtin_codecs():
        registry.register(codec)
    return registry


# Process-wide default. Treated read-only after import (additional codecs land in E2).
DEFAULT_REGISTRY = build_default_registry()
