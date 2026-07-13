"""Type codecs, the OID→codec registry, and the per-column result-decoding plan.

A :class:`Codec` knows how to encode a Python value to wire bytes and decode wire bytes back,
in both binary and text formats. The :class:`CodecRegistry` maps PostgreSQL type OIDs to
codecs. A live connection owns a database-specific registry so server-assigned OIDs never
cross sessions; registries remain ``threading.Lock``-guarded for safe publication, expose reads
as a :class:`types.MappingProxyType` snapshot, and **fail loud** on a conflicting
re-registration (never last-wins) — the chirp ``shapes`` registry discipline. The process-wide
default supplies immutable built-in facts to module consumers and fresh-registry construction.

The E1 spine shipped only the hottest OIDs (ints, text, bool, floats). The E2 long tail —
``numeric``, the temporal family, ``uuid``/``bytea``, ``json``/``jsonb``, and the parametric
array/composite/range/enum families — lands here, wired into :func:`build_default_registry`
from each family's ``LEAF_CODECS`` tuple and its parametric factories. Per-row decode
parallelism across free-threaded workers (epic E6) is built on the immutable snapshot this
registry hands out.

The other E2 deliverable is :func:`build_codec_plan`: given a :class:`~._messages.RowDescription`
and a registry snapshot, it precomputes one ``(bytes | None) -> Any`` decoder per column — the
right ``decode_binary``/``decode_text`` half chosen from each field's ``format_code``, ``None``
passed straight through for SQL NULL, parametric array/range/composite columns resolved against
the snapshot, and a UTF-8 / raw-bytes **text fallback** for any unregistered OID so an unknown
type never crashes the row path. The plan is a plain tuple of closures, computed once per result
set and reused for every row.

This module stays sans-I/O: bytes in, Python objects out; no socket, no anyio.
"""

from __future__ import annotations

import struct
import threading
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from chirp.data.drivers._pelt._messages import FieldDescription, RowDescription

    # ``DEFAULT_REGISTRY`` is materialized lazily via module ``__getattr__`` (see below) to stay
    # clear of the ``_codecs`` ↔ codec-family import cycle; declare it here so it is statically
    # visible to type checkers and ``from ._codecs import DEFAULT_REGISTRY`` callers.
    DEFAULT_REGISTRY: CodecRegistry

from chirp.data.drivers._pelt.errors import ProtocolError

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


def _e1_codecs() -> tuple[Codec, ...]:
    """The E1 hot-path leaf codecs defined inline in this module (ints, floats, bool, text)."""
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


# --- E2 leaf-family wiring --------------------------------------------------
# The E2 families live in sibling modules that import :class:`Codec` from *this* module. That is
# a true import cycle: ``_codecs`` cannot reference any sibling at *its own import time* (a
# sibling-first import would run this module to completion to satisfy ``from ._codecs import
# Codec`` while the sibling is only half-initialized — its ``LEAF_CODECS`` would not yet exist).
# So every sibling reference here is **call-time/lazy**: the sibling modules are imported inside
# the build/plan functions (and ``DEFAULT_REGISTRY`` is built lazily via ``__getattr__`` below),
# never during ``_codecs`` import. They are pure-Python, sans-I/O modules.


def _e2_leaf_codecs() -> tuple[Codec, ...]:
    """Every non-parametric E2 codec, gathered from each family's ``LEAF_CODECS`` tuple.

    Array/composite/range/enum families contribute *nothing* here — they are parametric (the
    element/field codec is only known at plan time), so their ``LEAF_CODECS`` are empty and they
    are wired via :func:`build_codec_plan` instead. The sibling imports are deferred to call time
    to break the ``_codecs`` ↔ family import cycle.
    """
    from chirp.data.drivers._pelt import (
        _codecs_json,
        _codecs_numeric,
        _codecs_temporal,
        _codecs_uuid_bytea,
    )

    return (
        *_codecs_numeric.LEAF_CODECS,
        *_codecs_temporal.LEAF_CODECS,
        *_codecs_uuid_bytea.LEAF_CODECS,
        *_codecs_json.LEAF_CODECS,
    )


def _builtin_codecs() -> tuple[Codec, ...]:
    """The full set of non-parametric codecs the default registry pre-loads (E1 + E2 leaves)."""
    return (*_e1_codecs(), *_e2_leaf_codecs())


def build_default_registry() -> CodecRegistry:
    """A fresh registry pre-loaded with the E1 hot-path codecs plus the E2 leaf families.

    Registration keeps the fail-loud conflict discipline: each OID is registered exactly once,
    so a duplicate OID across families (a packaging bug) raises :class:`ValueError` at build
    time rather than silently last-wins.
    """
    registry = CodecRegistry()
    for codec in _builtin_codecs():
        registry.register(codec)
    return registry


_DEFAULT_REGISTRY: CodecRegistry | None = None
# Guards the lazy first-build below. Without it, two threads under PYTHON_GIL=0 could both
# observe ``None`` and each build a *separate* registry — defeating the process-wide singleton
# (and contradicting the free-threading correctness pelt exists to guarantee).
_DEFAULT_REGISTRY_LOCK = threading.Lock()


def __getattr__(name: str) -> Any:
    """Build ``DEFAULT_REGISTRY`` lazily on first access.

    ``DEFAULT_REGISTRY`` cannot be built eagerly at module import: doing so reads each E2 family's
    ``LEAF_CODECS`` while a *family-first* import is still resolving its ``from ._codecs import
    Codec`` — the family is only half-initialized at that point, so the read would crash with a
    partial-init :class:`AttributeError`. Deferring the build to first attribute access keeps the
    process-wide default a one-liner for callers while staying cycle-safe under any import order.

    The build is double-checked-lock guarded so concurrent first accesses on free-threaded
    workers materialize exactly one registry. Treated read-only after creation; connections
    register extra codecs on a fresh :func:`build_default_registry` for per-database enums,
    arrays, ranges, and composites.
    """
    if name == "DEFAULT_REGISTRY":
        global _DEFAULT_REGISTRY
        registry = _DEFAULT_REGISTRY
        if registry is None:
            with _DEFAULT_REGISTRY_LOCK:
                registry = _DEFAULT_REGISTRY
                if registry is None:
                    registry = build_default_registry()
                    _DEFAULT_REGISTRY = registry
        return registry
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


# --- per-column result-decoding plan ----------------------------------------
def _array_element_oid_map() -> Mapping[int, int]:
    """Array OID → element OID (lazy import to stay clear of the family import cycle)."""
    from chirp.data.drivers._pelt import _codecs_array

    return _codecs_array.ARRAY_OID_TO_ELEMENT


def _range_element_oid_map() -> Mapping[int, int]:
    """Range OID → element OID, so the planner can resolve a parametric range column's element.

    Element OIDs cross-referenced from the leaf families: int4 23, int8 20, numeric 1700,
    timestamp 1114, timestamptz 1184, date 1082 — see ``pg_type.dat``. Lazy-imported to stay
    clear of the ``_codecs`` ↔ family import cycle.
    """
    from chirp.data.drivers._pelt import (
        _codecs_composite_range_enum as crange,
    )
    from chirp.data.drivers._pelt import (
        _codecs_numeric,
        _codecs_temporal,
    )

    return {
        crange.OID_INT4RANGE: OID_INT4,
        crange.OID_INT8RANGE: OID_INT8,
        crange.OID_NUMRANGE: _codecs_numeric.OID_NUMERIC,
        crange.OID_TSRANGE: _codecs_temporal.OID_TIMESTAMP,
        crange.OID_TSTZRANGE: _codecs_temporal.OID_TIMESTAMPTZ,
        crange.OID_DATERANGE: _codecs_temporal.OID_DATE,
    }


def _unsupported_binary_fallback(data: bytes) -> Any:
    """Reject binary bytes for an OID without a proven decoder."""
    del data
    msg = "PostgreSQL returned binary data for a type without a registered binary decoder"
    raise ProtocolError(
        msg,
        hint="Request text format for the column or register a codec for its server-assigned OID.",
    )


def _text_utf8_fallback(data: bytes) -> str:
    """Text-format fallback for an unregistered OID: decode UTF-8.

    PostgreSQL's text wire format is the type's ``typoutput`` string in the server encoding
    (UTF-8 for any modern deployment), so a faithful str is the safe, non-crashing default.
    """
    return data.decode("utf-8")


def _column_decoder(
    field: FieldDescription, snapshot: Mapping[int, Codec]
) -> Callable[[bytes], Any]:
    """Resolve the non-NULL decoder for one column from its OID + ``format_code``.

    ``format_code`` is ``1`` for binary and ``0`` for text (PostgreSQL's ``Bind``/``RowDescription``
    convention). A registered OID uses the matching half of its :class:`Codec`; a known
    array/range OID is resolved parametrically against ``snapshot``; an unregistered OID falls
    back to raw-bytes (binary) or UTF-8 (text) so the row path never crashes on an unknown type.
    """
    # Lazy family imports (call-time only — see the import-cycle note above _e2_leaf_codecs).
    from chirp.data.drivers._pelt import (
        _codecs_array,
    )
    from chirp.data.drivers._pelt import (
        _codecs_composite_range_enum as crange,
    )

    binary = field.format_code == 1
    codec = snapshot.get(field.type_oid)
    if codec is not None:
        return codec.decode_binary if binary else codec.decode_text

    # Parametric: a known array column whose element codec is in the snapshot.
    element_oid = _array_element_oid_map().get(field.type_oid)
    if element_oid is not None:
        element = snapshot.get(element_oid)
        if element is not None and binary:
            decode_elem = element.decode_binary
            return lambda data: _codecs_array.decode_array(data, decode_elem)

    # Parametric: a known range column whose element codec is in the snapshot.
    element_oid = _range_element_oid_map().get(field.type_oid)
    if element_oid is not None:
        element = snapshot.get(element_oid)
        if element is not None and binary:
            decode_elem = element.decode_binary
            return lambda data: crange.decode_range(data, decode_elem)

    # Unknown OID (or a parametric column we cannot resolve / a text-format parametric column):
    # preserve the faithful UTF-8 fallback for text. Binary data has no safe generic Python
    # interpretation, so fail loud if the server contradicts pelt's text negotiation.
    return _unsupported_binary_fallback if binary else _text_utf8_fallback


def result_format_codes(
    row_desc: RowDescription,
    registry_snapshot: Mapping[int, Codec],
) -> tuple[int, ...]:
    """Choose one explicit result format per described column.

    A registered codec opts into binary through ``prefers_binary``. Known
    parametric arrays and ranges opt in when their element codec is available.
    Every unresolved OID stays text, preserving PostgreSQL's lossless output
    fallback instead of requesting undecodable bytes.
    """
    array_elements = _array_element_oid_map()
    range_elements = _range_element_oid_map()
    formats: list[int] = []
    for field in row_desc.fields:
        codec = registry_snapshot.get(field.type_oid)
        if codec is not None:
            formats.append(1 if codec.prefers_binary else 0)
            continue
        element_oid = array_elements.get(field.type_oid)
        if element_oid is None:
            element_oid = range_elements.get(field.type_oid)
        formats.append(1 if element_oid in registry_snapshot else 0)
    return tuple(formats)


def with_result_formats(
    row_desc: RowDescription,
    formats: Sequence[int],
) -> RowDescription:
    """Copy a statement description with the formats selected by ``Bind``."""
    if len(formats) != len(row_desc.fields):
        msg = (
            f"result format count {len(formats)} does not match "
            f"row-description field count {len(row_desc.fields)}"
        )
        raise ValueError(msg)
    if any(code not in (0, 1) for code in formats):
        msg = "result format codes must be 0 (text) or 1 (binary)"
        raise ValueError(msg)
    return type(row_desc)(
        fields=tuple(
            replace(field, format_code=code)
            for field, code in zip(row_desc.fields, formats, strict=True)
        )
    )


def build_codec_plan(
    row_desc: RowDescription, registry_snapshot: Mapping[int, Codec]
) -> tuple[Callable[[bytes | None], Any], ...]:
    """Precompute one ``(bytes | None) -> Any`` decoder per column for a result set.

    Each returned decoder maps a raw column value (from a :class:`~._messages.DataRow`) to a
    Python object: ``None`` (SQL NULL) passes straight through as ``None``; otherwise the column
    bytes go through the resolved per-column decoder. Computing the plan once per
    :class:`~._messages.RowDescription` — rather than re-resolving the codec for every cell —
    keeps the per-row loop a tuple of bound closures, which is what makes free-threaded row decode
    cheap (epic E6). ``registry_snapshot`` is an immutable :meth:`CodecRegistry.snapshot` view, so
    the plan is lock-free.
    """
    decoders: list[Callable[[bytes | None], Any]] = []
    for field in row_desc.fields:
        decode = _column_decoder(field, registry_snapshot)

        def cell_decoder(value: bytes | None, _decode: Callable[[bytes], Any] = decode) -> Any:
            return None if value is None else _decode(value)

        decoders.append(cell_decoder)
    return tuple(decoders)
