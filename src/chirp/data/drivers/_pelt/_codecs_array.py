"""E2 codec family: PostgreSQL arrays (1-D and N-D), parametric on element type.

PostgreSQL models every array type as a distinct OID (``_int4`` = 1007, ``_text`` = 1009,
…) whose elements share one element OID. The binary wire layout is a fixed header followed
by a row-major run of length-prefixed element payloads:

    int32  ndim          -- number of dimensions (0 => empty array, header ends here)
    int32  flags         -- bit 0 set => the array contains at least one SQL NULL
    int32  element_oid   -- OID of the element type
    ndim * (             -- one pair per dimension
        int32 dim_length     -- number of elements along this dimension
        int32 lower_bound )  -- starting subscript (PostgreSQL default is 1)
    elements...          -- prod(dim_lengths) elements, row-major (last axis varies fastest)
        int32 length         -- byte length of this element (-1 => SQL NULL, no payload)
        byte  value[length]  -- the element payload, decoded by the element codec

Because element decoding resolves to a codec only at plan time (the element OID is known
from the array OID, but the *codec* is looked up against a registry snapshot), arrays are a
**parametric family**: this module exports pure ``decode_array`` / ``encode_array`` helpers
plus a :func:`make_array_codec` factory that closes over a concrete element codec, rather
than ready-to-register leaf codecs. :data:`LEAF_CODECS` is therefore empty.

This module touches no socket and no anyio — bytes in, nested Python lists out.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Any

from chirp.data.drivers._pelt._codecs import (
    OID_BOOL,
    OID_INT4,
    OID_INT8,
    OID_TEXT,
    Codec,
)
from chirp.data.drivers._pelt.errors import ProtocolError

if TYPE_CHECKING:
    from collections.abc import Callable

# --- array type OIDs (from pg_type.dat; ``_typename`` rows) -----------------
OID_ARRAY_BOOL = 1000
OID_ARRAY_BYTEA = 1001
OID_ARRAY_INT4 = 1007
OID_ARRAY_TEXT = 1009
OID_ARRAY_INT8 = 1016
OID_ARRAY_FLOAT8 = 1022
OID_ARRAY_NUMERIC = 1231
OID_ARRAY_TIMESTAMPTZ = 1185
OID_ARRAY_UUID = 2951

# Element OIDs referenced by the common arrays above but not yet defined in _codecs
# (their leaf codecs land elsewhere in E2). Kept local so this module stays self-contained.
_OID_BYTEA = 17
_OID_NUMERIC = 1700
_OID_TIMESTAMPTZ = 1184
_OID_UUID = 2950

#: Maps a common array OID to its element OID, so a planner can resolve the element codec.
ARRAY_OID_TO_ELEMENT: dict[int, int] = {
    OID_ARRAY_INT4: OID_INT4,  # _int4    1007 → int4    23
    OID_ARRAY_TEXT: OID_TEXT,  # _text    1009 → text    25
    OID_ARRAY_INT8: OID_INT8,  # _int8    1016 → int8    20
    OID_ARRAY_BOOL: OID_BOOL,  # _bool    1000 → bool    16
    OID_ARRAY_FLOAT8: 701,  # _float8  1022 → float8  701
    OID_ARRAY_UUID: _OID_UUID,  # _uuid    2951 → uuid    2950
    OID_ARRAY_NUMERIC: _OID_NUMERIC,  # _numeric 1231 → numeric 1700
    OID_ARRAY_TIMESTAMPTZ: _OID_TIMESTAMPTZ,  # _timestamptz 1185 → timestamptz 1184
    OID_ARRAY_BYTEA: _OID_BYTEA,  # _bytea   1001 → bytea   17
}

# Header layout is fixed-width Int32 fields; pre-built Structs avoid per-call recompilation.
_HEADER = struct.Struct(">iii")  # ndim, flags, element_oid
_DIM = struct.Struct(">ii")  # dim_length, lower_bound
_LEN = struct.Struct(">i")  # element byte length (or -1 for NULL)

_FLAG_HAS_NULLS = 1
#: PostgreSQL's default starting subscript when pelt builds an array from a Python list.
_DEFAULT_LOWER_BOUND = 1
#: PostgreSQL's hard cap on array dimensionality (``MAXDIM`` in ``src/include/c.h``). A header
#: claiming more dimensions than this is impossible on a real server, so we reject it outright:
#: a hostile ``ndim`` (e.g. ``2**31 - 1``) is a protocol fault on decode and caller misuse on
#: encode, even though the per-dimension truncation guard would also stop runaway allocation.
MAXDIM = 6


def _shape(value: list, ndim_hint: int | None) -> tuple[int, ...]:
    """Infer the per-dimension lengths of a (possibly nested) list.

    Walks the *first* element down each axis to read each dimension's length, then verifies
    every sibling matches — PostgreSQL arrays are rectangular, so a ragged nesting is a
    programmer error in the caller's value, raised as :class:`ValueError` (mirroring
    ``_builder.frame``'s misuse policy) rather than a protocol fault.
    """
    dims: list[int] = []
    node: Any = value
    while isinstance(node, list):
        dims.append(len(node))
        node = node[0] if node else None
        if ndim_hint is not None and len(dims) == ndim_hint:
            break
    shape = tuple(dims)
    _check_rectangular(value, shape, 0)
    return shape


def _check_rectangular(node: Any, shape: tuple[int, ...], depth: int) -> None:
    if depth >= len(shape):
        return
    if not isinstance(node, list) or len(node) != shape[depth]:
        msg = f"ragged array: expected length {shape[depth]} at depth {depth}, got {node!r}"
        raise ValueError(msg)
    for child in node:
        _check_rectangular(child, shape, depth + 1)


def _flatten(node: Any, depth: int, ndim: int, out: list) -> None:
    """Append the leaf elements of ``node`` to ``out`` in row-major order."""
    if depth == ndim:
        out.append(node)
        return
    for child in node:
        _flatten(child, depth + 1, ndim, out)


def _nest(flat: list, shape: tuple[int, ...], offset: int, depth: int) -> tuple[list, int]:
    """Rebuild a nested list of ``shape`` from the row-major ``flat`` run, returning the
    next consumption offset alongside the assembled level."""
    if depth == len(shape) - 1:
        end = offset + shape[depth]
        return flat[offset:end], end
    level: list = []
    for _ in range(shape[depth]):
        child, offset = _nest(flat, shape, offset, depth + 1)
        level.append(child)
    return level, offset


def decode_array(data: bytes, decode_elem: Callable[[bytes], Any]) -> list:
    """Decode a binary array payload into nested Python lists.

    ``decode_elem`` decodes one element's raw bytes (typically the element codec's
    ``decode_binary``); SQL NULL elements become ``None`` and never reach ``decode_elem``.
    A truncated or self-inconsistent payload raises :class:`ProtocolError` — arrays arrive
    from the framer, so a malformed body is a protocol fault, not caller misuse. The whole
    buffer must be consumed: a stray trailing byte (even after a complete array) raises
    :class:`ProtocolError` rather than being silently dropped, since it signals an upstream
    framing desync — unrecoverable on that connection.
    """
    if len(data) < _HEADER.size:
        msg = f"truncated array header: need {_HEADER.size} bytes, got {len(data)}"
        raise ProtocolError(msg)
    ndim, _flags, _element_oid = _HEADER.unpack_from(data, 0)
    if ndim < 0:
        msg = f"invalid array ndim {ndim}"
        raise ProtocolError(msg)
    if ndim > MAXDIM:
        msg = f"array ndim {ndim} exceeds PostgreSQL MAXDIM {MAXDIM}"
        raise ProtocolError(msg)
    if ndim == 0:
        # The zero-dimension header is the whole payload; any extra bytes are a desync.
        if len(data) != _HEADER.size:
            trailing = len(data) - _HEADER.size
            msg = f"array has {trailing} trailing byte(s) after empty (ndim=0) header"
            raise ProtocolError(msg)
        return []

    pos = _HEADER.size
    shape: list[int] = []
    for _ in range(ndim):
        if pos + _DIM.size > len(data):
            msg = "truncated array dimension header"
            raise ProtocolError(msg)
        dim_length, _lower = _DIM.unpack_from(data, pos)
        if dim_length < 0:
            msg = f"invalid array dimension length {dim_length}"
            raise ProtocolError(msg)
        shape.append(dim_length)
        pos += _DIM.size

    total = 1
    for dim_length in shape:
        total *= dim_length

    flat: list = []
    for _ in range(total):
        if pos + _LEN.size > len(data):
            msg = "truncated array element length prefix"
            raise ProtocolError(msg)
        (length,) = _LEN.unpack_from(data, pos)
        pos += _LEN.size
        if length == -1:
            flat.append(None)
            continue
        if length < 0:
            msg = f"invalid array element length {length}"
            raise ProtocolError(msg)
        if pos + length > len(data):
            msg = "truncated array element payload"
            raise ProtocolError(msg)
        flat.append(decode_elem(data[pos : pos + length]))
        pos += length

    if pos != len(data):
        trailing = len(data) - pos
        msg = f"array has {trailing} trailing byte(s) after {total} element(s)"
        raise ProtocolError(msg)

    nested, _consumed = _nest(flat, tuple(shape), 0, 0)
    return nested


def encode_array(
    value: list,
    *,
    element_oid: int,
    encode_elem: Callable[[Any], bytes],
    ndim_hint: int | None = None,
) -> bytes:
    """Encode a nested Python list into a binary array payload.

    ``encode_elem`` encodes one non-NULL element to its raw bytes (typically the element
    codec's ``encode_binary``); ``None`` elements are emitted as the ``-1`` NULL sentinel and
    set the has-nulls header flag. ``ndim_hint`` bounds dimension inference for the rare case
    of an array *of* lists (where the leaf type is itself a list); when ``None`` the shape is
    inferred by walking the nesting until a non-list leaf.

    Any array with **zero total elements** encodes as the canonical zero-dimension header,
    regardless of nesting depth — PostgreSQL flattens every empty array (``[]``, ``[[]]``,
    ``[[], []]``) to the same ``ndim=0`` form, and ``decode_array`` of that header returns a
    bare ``[]`` (so an empty nested input does not round-trip back to its original nesting).
    A nesting deeper than PostgreSQL's :data:`MAXDIM` is impossible on a real server and is
    rejected as :class:`ValueError` (caller misuse); a ragged (non-rectangular) ``value`` is
    likewise a :class:`ValueError`.
    """
    if not isinstance(value, list):
        msg = f"array value must be a list, got {type(value).__name__}"
        raise TypeError(msg)
    if not value:
        # Empty array: ndim=0, no nulls, element_oid recorded for the server's benefit.
        return _HEADER.pack(0, 0, element_oid)

    shape = _shape(value, ndim_hint)
    ndim = len(shape)
    if ndim > MAXDIM:
        msg = f"array ndim {ndim} exceeds PostgreSQL MAXDIM {MAXDIM}"
        raise ValueError(msg)
    if any(dim_length == 0 for dim_length in shape):
        # Zero elements anywhere collapses to the canonical empty header (PG flattens e.g.
        # [[]] / [[], []] to ndim=0); avoids emitting a positive-ndim zero-length axis.
        return _HEADER.pack(0, 0, element_oid)

    flat: list = []
    _flatten(value, 0, ndim, flat)

    parts: list[bytes] = []
    has_nulls = False
    for elem in flat:
        if elem is None:
            has_nulls = True
            parts.append(_LEN.pack(-1))
            continue
        encoded = encode_elem(elem)
        parts.append(_LEN.pack(len(encoded)))
        parts.append(encoded)

    header = bytearray()
    header += _HEADER.pack(ndim, _FLAG_HAS_NULLS if has_nulls else 0, element_oid)
    for dim_length in shape:
        header += _DIM.pack(dim_length, _DEFAULT_LOWER_BOUND)
    return bytes(header) + b"".join(parts)


def make_array_codec(
    *,
    array_oid: int,
    name: str,
    element_oid: int,
    element_codec: Codec,
) -> Codec:
    """Build an array :class:`Codec` that wraps ``element_codec``'s binary functions.

    The returned codec decodes/encodes the *binary* array format only; the text path falls
    back to the binary functions (PostgreSQL's text array syntax — ``{1,2,3}`` with quoting
    and escaping rules — is out of scope here, since pelt prefers binary for arrays). The
    factory is parametric: callers resolve ``element_codec`` against a registry snapshot at
    plan time and pass it in, keeping this module free of any global registry coupling.
    """
    decode_elem = element_codec.decode_binary
    encode_elem = element_codec.encode_binary

    def decode_binary(data: bytes) -> list:
        return decode_array(data, decode_elem)

    def encode_binary(value: Any) -> bytes:
        return encode_array(value, element_oid=element_oid, encode_elem=encode_elem)

    return Codec(
        oid=array_oid,
        name=name,
        decode_binary=decode_binary,
        decode_text=decode_binary,
        encode_binary=encode_binary,
        encode_text=encode_binary,
        prefers_binary=True,
    )


#: Arrays are a parametric family — no element-agnostic leaf codec can be registered.
LEAF_CODECS: tuple[Codec, ...] = ()


__all__ = [
    "ARRAY_OID_TO_ELEMENT",
    "LEAF_CODECS",
    "OID_ARRAY_BOOL",
    "OID_ARRAY_BYTEA",
    "OID_ARRAY_FLOAT8",
    "OID_ARRAY_INT4",
    "OID_ARRAY_INT8",
    "OID_ARRAY_NUMERIC",
    "OID_ARRAY_TEXT",
    "OID_ARRAY_TIMESTAMPTZ",
    "OID_ARRAY_UUID",
    "decode_array",
    "encode_array",
    "make_array_codec",
]
