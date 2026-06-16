"""E2 parametric codecs: composite (record), range, and enum types.

Unlike the leaf codecs in :mod:`._codecs` (one OID, one fixed Python type), these three
families are *parametric*: a composite decodes through a per-field codec list, a range
decodes through its element codec, and an enum's OID is assigned per-database at
``CREATE TYPE`` time. So this module exports **factories** that close over the element/field
codecs (or, for enums, the runtime OID) and hand back a ready-to-register :class:`Codec`,
plus the standalone ``decode_*``/``encode_*`` primitives the factories wrap. The
:data:`LEAF_CODECS` tuple is empty — there is no non-parametric codec to pre-register here.

Wire layouts are bit-exact to the PostgreSQL binary protocol (``src/backend/utils/adt``):

* **record** (``record_recv``): ``int32 nfields``; then per field ``int32 column_oid``,
  ``int32 length`` (``-1`` ⇒ SQL NULL), then ``length`` raw bytes.
* **range** (``range_recv``): ``uint8 flags``; then, for each *finite* bound that is present,
  ``int32 length`` + ``length`` raw bytes. Flag bits (``rangetypes.h``): ``0x01`` empty,
  ``0x02`` lower-inclusive, ``0x04`` upper-inclusive, ``0x08`` lower-infinite,
  ``0x10`` upper-infinite.
* **enum**: the value is just its label text; enums share ``enum_recv``/``enum_out`` which are
  UTF-8 in/out, so the codec is a thin TEXT alias bound to the per-DB OID.

Decoding a record yields a plain ``tuple`` (positional) — mapping field names onto a
``dict``/Row is a plan-layer concern (epic E6), not the codec's. Malformed wire bytes raise
:class:`ProtocolError` (the sans-I/O fault channel); bad *factory* arguments raise
``ValueError`` (programmer misuse), mirroring :func:`._builder.frame`.

Live-PG parity is deferred to the E4/E6 integration suite; here we prove the layouts against
hand-built wire vectors.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chirp.data.drivers._pelt._codecs import Codec
from chirp.data.drivers._pelt.errors import ProtocolError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# --- common range type OIDs (from pg_type.dat) ------------------------------
OID_INT4RANGE = 3904
OID_NUMRANGE = 3906
OID_TSRANGE = 3908
OID_TSTZRANGE = 3910
OID_DATERANGE = 3912
OID_INT8RANGE = 3926

# Range flag bits (PostgreSQL src/include/utils/rangetypes.h).
RANGE_EMPTY = 0x01
RANGE_LB_INC = 0x02
RANGE_UB_INC = 0x04
RANGE_LB_INF = 0x08
RANGE_UB_INF = 0x10

_PACK_INT32 = struct.Struct(">i")  # signed: nfields count + length fields (-1 = SQL NULL)
_PACK_OID = struct.Struct(">I")  # unsigned: PostgreSQL Oid is uint32 (0..4294967295)
_PACK_UINT8 = struct.Struct(">B")

# No non-parametric codec ships from this module — every family is built per-type.
LEAF_CODECS: tuple[Codec, ...] = ()


# --- record / composite -----------------------------------------------------
def decode_record(
    data: bytes, field_decoders: Sequence[Callable[[bytes], Any] | None]
) -> tuple[Any, ...]:
    """Decode binary ``record`` wire bytes into a positional :class:`tuple`.

    ``field_decoders[i]`` decodes column ``i``'s raw bytes; a ``None`` entry passes the raw
    bytes through undecoded (the OID had no registered codec). SQL NULL columns become
    ``None`` regardless of the decoder. The on-wire ``nfields`` count is authoritative; a
    decoder-list length mismatch raises :class:`ProtocolError` rather than silently truncating.
    """
    view = memoryview(data)
    pos = 0
    end = len(view)
    if end - pos < 4:
        msg = f"truncated record header: wanted 4 bytes, have {end - pos}"
        raise ProtocolError(msg)
    nfields = _PACK_INT32.unpack(view[pos : pos + 4])[0]
    pos += 4
    if nfields < 0:
        msg = f"negative record field count {nfields}"
        raise ProtocolError(msg)
    if nfields != len(field_decoders):
        msg = (
            f"record field count {nfields} does not match "
            f"{len(field_decoders)} supplied field decoder(s)"
        )
        raise ProtocolError(msg)

    out: list[Any] = []
    for i in range(nfields):
        if end - pos < 8:
            msg = f"truncated record field {i} header at offset {pos}"
            raise ProtocolError(msg)
        # column_oid (uint32) is wire metadata; the decoder is keyed positionally, so the value
        # is read (to advance past it correctly) but discarded. It is unsigned: a high-bit-set
        # OID would read negative under a signed struct, so use _PACK_OID for symmetry with the
        # encode path even though the result is unused.
        _PACK_OID.unpack(view[pos : pos + 4])
        pos += 4
        length = _PACK_INT32.unpack(view[pos : pos + 4])[0]
        pos += 4
        if length == -1:
            out.append(None)
            continue
        if length < 0:
            msg = f"invalid record field {i} length {length}"
            raise ProtocolError(msg)
        if end - pos < length:
            msg = f"truncated record field {i}: wanted {length} bytes at offset {pos}"
            raise ProtocolError(msg)
        raw = bytes(view[pos : pos + length])
        pos += length
        decoder = field_decoders[i]
        out.append(raw if decoder is None else decoder(raw))

    if pos != end:
        msg = f"record has {end - pos} trailing byte(s) after {nfields} field(s)"
        raise ProtocolError(msg)
    return tuple(out)


def encode_record(
    values: Sequence[Any],
    field_oids: Sequence[int],
    field_encoders: Sequence[Callable[[Any], bytes] | None],
) -> bytes:
    """Encode a positional sequence into binary ``record`` wire bytes.

    ``field_oids[i]`` is written as the column OID; ``field_encoders[i]`` turns a non-NULL
    value into raw bytes (a ``None`` encoder requires the value to already be ``bytes``).
    ``None`` values are emitted as SQL NULL (length ``-1``). The three sequences must be the
    same length — a mismatch is programmer misuse and raises ``ValueError``.
    """
    if not (len(values) == len(field_oids) == len(field_encoders)):
        msg = (
            f"record encode arity mismatch: {len(values)} value(s), "
            f"{len(field_oids)} oid(s), {len(field_encoders)} encoder(s)"
        )
        raise ValueError(msg)
    parts: list[bytes] = [_PACK_INT32.pack(len(values))]
    for value, oid, encoder in zip(values, field_oids, field_encoders, strict=True):
        # Oid is an unsigned 32-bit value; an OID > 2**31-1 (reachable as the server's OID
        # counter advances) must not overflow a signed pack. A non-uint32 OID is caller misuse.
        if not 0 <= oid <= 0xFFFFFFFF:
            msg = f"record field OID {oid} out of uint32 range (0..4294967295)"
            raise ValueError(msg)
        parts.append(_PACK_OID.pack(oid))
        if value is None:
            parts.append(_PACK_INT32.pack(-1))
            continue
        raw = value if encoder is None else encoder(value)
        parts.append(_PACK_INT32.pack(len(raw)))
        parts.append(raw)
    return b"".join(parts)


def make_record_codec(
    *,
    oid: int,
    name: str,
    field_oids: Sequence[int],
    field_decoders: Sequence[Callable[[bytes], Any] | None],
    field_encoders: Sequence[Callable[[Any], bytes] | None],
) -> Codec:
    """Build a binary-only composite/record :class:`Codec` from per-field codecs.

    The three field sequences are positional and must be the same length; a mismatch raises
    ``ValueError``. Text format is not modelled for composites — PostgreSQL's text record
    syntax (quoted, comma-separated) is a plan-layer concern — so ``decode_text``/
    ``encode_text`` raise :class:`ProtocolError` if reached.
    """
    if not (len(field_oids) == len(field_decoders) == len(field_encoders)):
        msg = (
            f"record codec arity mismatch for {name!r}: {len(field_oids)} oid(s), "
            f"{len(field_decoders)} decoder(s), {len(field_encoders)} encoder(s)"
        )
        raise ValueError(msg)
    oids = tuple(field_oids)
    decoders = tuple(field_decoders)
    encoders = tuple(field_encoders)

    def decode_binary(data: bytes) -> tuple[Any, ...]:
        return decode_record(data, decoders)

    def encode_binary(value: Any) -> bytes:
        return encode_record(value, oids, encoders)

    def _no_text(_: Any) -> Any:
        msg = f"text format is unsupported for composite type {name!r}"
        raise ProtocolError(msg)

    return Codec(
        oid=oid,
        name=name,
        decode_binary=decode_binary,
        decode_text=_no_text,
        encode_binary=encode_binary,
        encode_text=_no_text,
    )


# --- range ------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Range:
    """An immutable PostgreSQL range value.

    ``lower``/``upper`` are the decoded bound values, or ``None`` for an infinite (unbounded)
    or absent bound. ``lower_inc``/``upper_inc`` flag inclusive bounds. ``empty`` marks the
    empty range, in which case the bounds carry no meaning.
    """

    lower: Any = None
    upper: Any = None
    lower_inc: bool = False
    upper_inc: bool = False
    empty: bool = False


def decode_range(data: bytes, element_decode: Callable[[bytes], Any]) -> Range:
    """Decode binary ``range`` wire bytes into a :class:`Range`.

    A finite, present bound is laid out as ``int32 length`` + ``length`` element bytes, decoded
    via ``element_decode``. Infinite bounds carry no payload. The empty range carries only the
    flags byte. Truncation or a stray trailing byte raises :class:`ProtocolError`.
    """
    view = memoryview(data)
    if len(view) < 1:
        msg = "truncated range: missing flags byte"
        raise ProtocolError(msg)
    flags = view[0]
    pos = 1
    end = len(view)

    if flags & RANGE_EMPTY:
        if pos != end:
            msg = f"empty range has {end - pos} trailing byte(s)"
            raise ProtocolError(msg)
        return Range(empty=True)

    def _read_bound(which: str) -> Any:
        nonlocal pos
        if end - pos < 4:
            msg = f"truncated range {which} bound length at offset {pos}"
            raise ProtocolError(msg)
        length = _PACK_INT32.unpack(view[pos : pos + 4])[0]
        pos += 4
        if length < 0:
            msg = f"invalid range {which} bound length {length}"
            raise ProtocolError(msg)
        if end - pos < length:
            msg = f"truncated range {which} bound: wanted {length} bytes at offset {pos}"
            raise ProtocolError(msg)
        raw = bytes(view[pos : pos + length])
        pos += length
        return element_decode(raw)

    lower: Any = None
    upper: Any = None
    lower_inf = bool(flags & RANGE_LB_INF)
    upper_inf = bool(flags & RANGE_UB_INF)
    if not lower_inf:
        lower = _read_bound("lower")
    if not upper_inf:
        upper = _read_bound("upper")

    if pos != end:
        msg = f"range has {end - pos} trailing byte(s)"
        raise ProtocolError(msg)
    # PostgreSQL canonicalizes an infinite bound to inclusive=false (range_serialize /
    # make_range clear the inclusive bit for any infinite bound). A canonical PG payload never
    # sets RANGE_LB_INC alongside RANGE_LB_INF, but a hand-built or non-canonical buffer might;
    # mask the inclusive flag against the infinity flag so decode reports the same canonical form
    # encode emits, keeping the round-trip exact.
    return Range(
        lower=lower,
        upper=upper,
        lower_inc=bool(flags & RANGE_LB_INC) and not lower_inf,
        upper_inc=bool(flags & RANGE_UB_INC) and not upper_inf,
        empty=False,
    )


def encode_range(value: Range, element_encode: Callable[[Any], bytes]) -> bytes:
    """Encode a :class:`Range` into binary ``range`` wire bytes.

    An empty range is a lone flags byte. Otherwise the flags byte is followed by each present
    finite bound (``int32 length`` + element bytes); a bound is treated as infinite when its
    value is ``None``. Inclusivity flags ride along — except for an infinite bound, whose
    inclusive bit is always cleared to match PostgreSQL's canonical wire form (range_serialize /
    make_range force an infinite bound to inclusive=false). So ``Range(lower=None,
    lower_inc=True)`` serializes with RANGE_LB_INC cleared, not RANGE_LB_INC | RANGE_LB_INF.
    """
    if value.empty:
        return _PACK_UINT8.pack(RANGE_EMPTY)

    flags = 0
    lower_inf = value.lower is None
    upper_inf = value.upper is None
    if value.lower_inc and not lower_inf:
        flags |= RANGE_LB_INC
    if value.upper_inc and not upper_inf:
        flags |= RANGE_UB_INC
    if lower_inf:
        flags |= RANGE_LB_INF
    if upper_inf:
        flags |= RANGE_UB_INF

    parts: list[bytes] = [_PACK_UINT8.pack(flags)]
    if not lower_inf:
        raw = element_encode(value.lower)
        parts.append(_PACK_INT32.pack(len(raw)))
        parts.append(raw)
    if not upper_inf:
        raw = element_encode(value.upper)
        parts.append(_PACK_INT32.pack(len(raw)))
        parts.append(raw)
    return b"".join(parts)


def make_range_codec(
    *,
    oid: int,
    name: str,
    element_decode: Callable[[bytes], Any],
    element_encode: Callable[[Any], bytes],
) -> Codec:
    """Build a binary-only range :class:`Codec` from its element codec's decode/encode pair.

    Text format (PostgreSQL's ``[lo,hi)`` syntax) is a plan-layer concern and is not modelled;
    ``decode_text``/``encode_text`` raise :class:`ProtocolError` if reached.
    """

    def decode_binary(data: bytes) -> Range:
        return decode_range(data, element_decode)

    def encode_binary(value: Any) -> bytes:
        return encode_range(value, element_encode)

    def _no_text(_: Any) -> Any:
        msg = f"text format is unsupported for range type {name!r}"
        raise ProtocolError(msg)

    return Codec(
        oid=oid,
        name=name,
        decode_binary=decode_binary,
        decode_text=_no_text,
        encode_binary=encode_binary,
        encode_text=_no_text,
    )


# --- enum -------------------------------------------------------------------
def make_enum_codec(oid: int, name: str) -> Codec:
    """Build a :class:`Codec` for a user-defined enum at its per-database ``oid``.

    Enums are assigned dynamic OIDs at ``CREATE TYPE`` time, so there is no static codec to
    pre-register — the connection discovers the OID and calls this factory. On the wire an enum
    value is just its label, identical in binary and text format, so the codec is a thin UTF-8
    ``str`` alias (text-preferred, like :func:`._codecs._text_codec`).
    """

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


__all__ = (
    "LEAF_CODECS",
    "OID_DATERANGE",
    "OID_INT4RANGE",
    "OID_INT8RANGE",
    "OID_NUMRANGE",
    "OID_TSRANGE",
    "OID_TSTZRANGE",
    "RANGE_EMPTY",
    "RANGE_LB_INC",
    "RANGE_LB_INF",
    "RANGE_UB_INC",
    "RANGE_UB_INF",
    "Range",
    "decode_range",
    "decode_record",
    "encode_range",
    "encode_record",
    "make_enum_codec",
    "make_range_codec",
    "make_record_codec",
)
