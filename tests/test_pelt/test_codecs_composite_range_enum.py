"""E2 (#255) — composite/record, range, and enum codec round-trips + known wire vectors.

Element/field codecs are stubbed with the int4 / text primitives so the parametric layouts
are exercised without depending on the full registry. Bit-exact vectors are cited against the
PostgreSQL binary wire layout; live-PG parity is deferred to the E4/E6 integration suite.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt._codecs_composite_range_enum import (
    LEAF_CODECS,
    OID_INT4RANGE,
    RANGE_EMPTY,
    RANGE_LB_INC,
    RANGE_LB_INF,
    RANGE_UB_INC,
    Range,
    decode_range,
    decode_record,
    encode_range,
    encode_record,
    make_enum_codec,
    make_range_codec,
    make_record_codec,
)
from chirp.data.drivers._pelt.errors import ProtocolError

# OIDs used by the stub field/element codecs (mirror _codecs.py).
_OID_INT4 = 23
_OID_TEXT = 25


# --- stub element/field codecs ----------------------------------------------
def _int4_decode(data: bytes) -> int:
    return int.from_bytes(data, "big", signed=True)


def _int4_encode(value: object) -> bytes:
    return int(value).to_bytes(4, "big", signed=True)


def _text_decode(data: bytes) -> str:
    return data.decode("utf-8")


def _text_encode(value: object) -> bytes:
    return str(value).encode("utf-8")


# --- LEAF_CODECS contract ---------------------------------------------------
@pytest.mark.issue(255)
def test_leaf_codecs_is_empty():
    # All three families are parametric; nothing to pre-register.
    assert LEAF_CODECS == ()


@pytest.mark.issue(255)
def test_module_declares_all_export_surface():
    # The pelt-codec export convention: every codec module declares __all__ listing its public
    # surface (LEAF_CODECS + OID consts + factories), matching _codecs_array / _codecs_numeric.
    import chirp.data.drivers._pelt._codecs_composite_range_enum as mod

    assert hasattr(mod, "__all__"), "module must declare __all__"
    exported = set(mod.__all__)
    expected = {
        "LEAF_CODECS",
        "OID_INT4RANGE",
        "OID_NUMRANGE",
        "OID_TSRANGE",
        "OID_TSTZRANGE",
        "OID_DATERANGE",
        "OID_INT8RANGE",
        "RANGE_EMPTY",
        "RANGE_LB_INC",
        "RANGE_UB_INC",
        "RANGE_LB_INF",
        "RANGE_UB_INF",
        "Range",
        "decode_record",
        "encode_record",
        "decode_range",
        "encode_range",
        "make_record_codec",
        "make_range_codec",
        "make_enum_codec",
    }
    assert exported == expected
    # Every exported name must actually resolve on the module (no stale entries).
    for name in mod.__all__:
        assert hasattr(mod, name), f"__all__ lists missing name {name!r}"


# === RECORD / COMPOSITE =====================================================
@pytest.mark.issue(255)
def test_record_known_vector():
    # Wire layout (record_recv): int32 nfields; per field int32 oid, int32 len(-1=NULL), bytes.
    # Record = (int4 1, int4 NULL, text "hi").
    wire = (
        b"\x00\x00\x00\x03"  # nfields = 3
        b"\x00\x00\x00\x17\x00\x00\x00\x04\x00\x00\x00\x01"  # oid 23, len 4, value 1
        b"\x00\x00\x00\x17\xff\xff\xff\xff"  # oid 23, len -1 (NULL)
        b"\x00\x00\x00\x19\x00\x00\x00\x02hi"  # oid 25, len 2, "hi"
    )
    decoders = (_int4_decode, _int4_decode, _text_decode)
    assert decode_record(wire, decoders) == (1, None, "hi")


@pytest.mark.issue(255)
def test_record_encode_known_vector():
    wire = encode_record(
        (1, None, "hi"),
        (_OID_INT4, _OID_INT4, _OID_TEXT),
        (_int4_encode, None, _text_encode),
    )
    expected = (
        b"\x00\x00\x00\x03"
        b"\x00\x00\x00\x17\x00\x00\x00\x04\x00\x00\x00\x01"
        b"\x00\x00\x00\x17\xff\xff\xff\xff"
        b"\x00\x00\x00\x19\x00\x00\x00\x02hi"
    )
    assert wire == expected


@pytest.mark.issue(255)
def test_record_none_decoder_passes_raw_bytes():
    wire = (
        b"\x00\x00\x00\x01"  # nfields = 1
        b"\x00\x00\x00\x17\x00\x00\x00\x04\x00\x00\x00\x07"  # oid 23, len 4, raw 0x07
    )
    # A None decoder leaves the column as raw bytes.
    assert decode_record(wire, (None,)) == (b"\x00\x00\x00\x07",)


@pytest.mark.issue(255)
def test_record_empty():
    # Zero-field record is just the count.
    assert decode_record(b"\x00\x00\x00\x00", ()) == ()
    assert encode_record((), (), ()) == b"\x00\x00\x00\x00"


@pytest.mark.issue(255)
@given(
    a=st.integers(min_value=-(2**31), max_value=2**31 - 1),
    b=st.text(),
    a_null=st.booleans(),
)
def test_record_round_trip(a, b, a_null):
    values = (None if a_null else a, b)
    oids = (_OID_INT4, _OID_TEXT)
    encoders = (_int4_encode, _text_encode)
    decoders = (_int4_decode, _text_decode)
    wire = encode_record(values, oids, encoders)
    assert decode_record(wire, decoders) == values


@pytest.mark.issue(255)
def test_record_codec_round_trip():
    codec = make_record_codec(
        oid=99999,
        name="my_composite",
        field_oids=(_OID_INT4, _OID_TEXT),
        field_decoders=(_int4_decode, _text_decode),
        field_encoders=(_int4_encode, _text_encode),
    )
    value = (42, "row")
    assert codec.decode_binary(codec.encode_binary(value)) == value


@pytest.mark.issue(255)
def test_record_codec_arity_mismatch_is_value_error():
    with pytest.raises(ValueError, match="arity mismatch"):
        make_record_codec(
            oid=99999,
            name="bad",
            field_oids=(_OID_INT4,),
            field_decoders=(_int4_decode, _text_decode),
            field_encoders=(_int4_encode,),
        )


@pytest.mark.issue(255)
def test_record_codec_text_is_unsupported():
    codec = make_record_codec(
        oid=99999,
        name="c",
        field_oids=(_OID_INT4,),
        field_decoders=(_int4_decode,),
        field_encoders=(_int4_encode,),
    )
    with pytest.raises(ProtocolError, match="text format is unsupported"):
        codec.decode_text(b"x")
    with pytest.raises(ProtocolError, match="text format is unsupported"):
        codec.encode_text((1,))


@pytest.mark.issue(255)
def test_record_decoder_count_mismatch_raises_protocol_error():
    wire = b"\x00\x00\x00\x02"  # claims 2 fields
    with pytest.raises(ProtocolError, match="does not match"):
        decode_record(wire, (_int4_decode,))  # only 1 decoder supplied


@pytest.mark.issue(255)
def test_record_truncated_header_raises_protocol_error():
    with pytest.raises(ProtocolError, match="truncated record header"):
        decode_record(b"\x00\x00", ())


@pytest.mark.issue(255)
def test_record_truncated_field_payload_raises_protocol_error():
    wire = (
        b"\x00\x00\x00\x01"
        b"\x00\x00\x00\x17\x00\x00\x00\x04\x00\x00"  # claims len 4 but only 2 bytes follow
    )
    with pytest.raises(ProtocolError, match="truncated record field"):
        decode_record(wire, (_int4_decode,))


@pytest.mark.issue(255)
def test_record_trailing_bytes_raise_protocol_error():
    wire = (
        b"\x00\x00\x00\x01"
        b"\x00\x00\x00\x17\x00\x00\x00\x04\x00\x00\x00\x01"
        b"\xde\xad"  # stray trailing bytes
    )
    with pytest.raises(ProtocolError, match="trailing byte"):
        decode_record(wire, (_int4_decode,))


@pytest.mark.issue(255)
def test_encode_record_arity_mismatch_is_value_error():
    with pytest.raises(ValueError, match="arity mismatch"):
        encode_record((1, 2), (_OID_INT4,), (_int4_encode,))


@pytest.mark.issue(255)
def test_record_high_oid_known_vector():
    # PostgreSQL's Oid is an UNSIGNED uint32, so the column OID is written big-endian unsigned.
    # An OID with the high bit set (here 0x80000064 = 2**31 + 100) would overflow a signed '>i'
    # pack with struct.error; the unsigned '>I' path round-trips it exactly.
    high_oid = 2**31 + 100  # 0x80000064
    wire = encode_record((1,), (high_oid,), (_int4_encode,))
    expected = (
        b"\x00\x00\x00\x01"  # nfields = 1
        b"\x80\x00\x00\x64"  # column oid 0x80000064 (uint32, high bit set)
        b"\x00\x00\x00\x04\x00\x00\x00\x01"  # len 4, value 1
    )
    assert wire == expected
    # Decode tolerates the high-bit OID (it is read as uint32 then discarded, not parsed signed).
    assert decode_record(wire, (_int4_decode,)) == (1,)


@pytest.mark.issue(255)
def test_record_max_oid_round_trips():
    # The full uint32 ceiling (4294967295 = 0xFFFFFFFF) must not be mistaken for a -1 NULL
    # sentinel or otherwise overflow; it lives in the OID field, distinct from the length field.
    max_oid = 0xFFFFFFFF
    wire = encode_record((7,), (max_oid,), (_int4_encode,))
    assert wire[4:8] == b"\xff\xff\xff\xff"  # column oid = 0xFFFFFFFF
    assert decode_record(wire, (_int4_decode,)) == (7,)


@pytest.mark.issue(255)
def test_record_oid_out_of_uint32_range_is_value_error():
    # An OID outside 0..2**32-1 is programmer misuse of the factory args, raised as ValueError
    # (mirroring _builder.frame), never a bare struct.error.
    with pytest.raises(ValueError, match="out of uint32 range"):
        encode_record((1,), (2**32,), (_int4_encode,))
    with pytest.raises(ValueError, match="out of uint32 range"):
        encode_record((1,), (-1,), (_int4_encode,))


# === RANGE ==================================================================
@pytest.mark.issue(255)
def test_range_known_vector_int4range():
    # Wire layout (range_recv): uint8 flags; then each present finite bound as int32 len + bytes.
    # int4range [1,10): lower-inclusive only → flags 0x02.
    wire = (
        b"\x02"  # flags: RANGE_LB_INC
        b"\x00\x00\x00\x04\x00\x00\x00\x01"  # lower bound: len 4, value 1
        b"\x00\x00\x00\x04\x00\x00\x00\x0a"  # upper bound: len 4, value 10
    )
    assert wire[0] == RANGE_LB_INC
    r = decode_range(wire, _int4_decode)
    assert r == Range(lower=1, upper=10, lower_inc=True, upper_inc=False, empty=False)


@pytest.mark.issue(255)
def test_range_encode_known_vector_int4range():
    wire = encode_range(
        Range(lower=1, upper=10, lower_inc=True, upper_inc=False),
        _int4_encode,
    )
    expected = b"\x02\x00\x00\x00\x04\x00\x00\x00\x01\x00\x00\x00\x04\x00\x00\x00\x0a"
    assert wire == expected


@pytest.mark.issue(255)
def test_range_empty_known_vector():
    # Empty range is a lone flags byte (0x01).
    wire = b"\x01"
    assert wire[0] == RANGE_EMPTY
    r = decode_range(wire, _int4_decode)
    assert r.empty is True
    assert encode_range(Range(empty=True), _int4_encode) == b"\x01"


@pytest.mark.issue(255)
def test_range_infinite_bound_known_vector():
    # (,5]: lower-infinite (0x08) + upper-inclusive (0x04) → flags 0x0c; only the upper bound
    # carries a payload (infinite bounds have no length/bytes on the wire).
    wire = (
        b"\x0c"  # flags: RANGE_LB_INF | RANGE_UB_INC
        b"\x00\x00\x00\x04\x00\x00\x00\x05"  # upper bound: len 4, value 5
    )
    r = decode_range(wire, _int4_decode)
    assert r == Range(lower=None, upper=5, lower_inc=False, upper_inc=True, empty=False)
    # Round-trip back to the same vector.
    assert encode_range(r, _int4_encode) == wire


@pytest.mark.issue(255)
def test_range_fully_unbounded():
    # (,): both bounds infinite → flags 0x18, no payload.
    wire = encode_range(Range(lower=None, upper=None), _int4_encode)
    assert wire == b"\x18"
    r = decode_range(wire, _int4_decode)
    assert r.lower is None
    assert r.upper is None
    assert r.empty is False


@pytest.mark.issue(255)
def test_range_infinite_bound_clears_inclusive_flag():
    # PostgreSQL canonicalizes an infinite bound to inclusive=false (range_serialize /
    # make_range clear the inclusive bit for any infinite bound). A Range with an infinite
    # lower bound but lower_inc=True must serialize with the lower-inclusive bit CLEARED — the
    # flags byte is RANGE_LB_INF alone (0x08), not RANGE_LB_INC | RANGE_LB_INF (0x0a). Otherwise
    # pelt would emit a non-canonical flags byte that disagrees with PG's own wire output.
    r = Range(lower=None, upper=5, lower_inc=True, upper_inc=True, empty=False)
    wire = encode_range(r, _int4_encode)
    # Exact flags byte: only RANGE_LB_INF set on the lower side (inclusive cleared); the upper
    # bound is finite so its inclusive bit (RANGE_UB_INC = 0x04) survives.
    expected = (
        b"\x0c"  # flags: RANGE_LB_INF (0x08) | RANGE_UB_INC (0x04) — NOT RANGE_LB_INC
        b"\x00\x00\x00\x04\x00\x00\x00\x05"  # upper bound: len 4, value 5
    )
    assert wire == expected
    assert wire[0] == RANGE_LB_INF | RANGE_UB_INC
    assert not (wire[0] & RANGE_LB_INC), "infinite lower bound must clear the inclusive bit"
    # Decode agrees on the canonical form: the infinite lower bound reports lower_inc=False.
    assert decode_range(wire, _int4_decode) == Range(
        lower=None, upper=5, lower_inc=False, upper_inc=True, empty=False
    )


@pytest.mark.issue(255)
@given(
    lo=st.integers(min_value=-(2**31), max_value=2**31 - 1),
    hi=st.integers(min_value=-(2**31), max_value=2**31 - 1),
    lo_inc=st.booleans(),
    hi_inc=st.booleans(),
    lo_inf=st.booleans(),
    hi_inf=st.booleans(),
)
def test_range_round_trip(lo, hi, lo_inc, hi_inc, lo_inf, hi_inf):
    r = Range(
        lower=None if lo_inf else lo,
        upper=None if hi_inf else hi,
        lower_inc=lo_inc,
        upper_inc=hi_inc,
        empty=False,
    )
    wire = encode_range(r, _int4_encode)
    # PG canonicalizes an infinite bound to inclusive=false, so encode/decode settle on that
    # canonical form. Compare against the canonicalized Range, not the raw input.
    canonical = Range(
        lower=r.lower,
        upper=r.upper,
        lower_inc=lo_inc and not lo_inf,
        upper_inc=hi_inc and not hi_inf,
        empty=False,
    )
    assert decode_range(wire, _int4_decode) == canonical


@pytest.mark.issue(255)
def test_range_empty_round_trip():
    r = Range(empty=True)
    assert decode_range(encode_range(r, _int4_encode), _int4_decode) == r


@pytest.mark.issue(255)
def test_range_codec_round_trip():
    codec = make_range_codec(
        oid=OID_INT4RANGE,
        name="int4range",
        element_decode=_int4_decode,
        element_encode=_int4_encode,
    )
    value = Range(lower=3, upper=99, lower_inc=True, upper_inc=False)
    assert codec.decode_binary(codec.encode_binary(value)) == value


@pytest.mark.issue(255)
def test_range_codec_text_is_unsupported():
    codec = make_range_codec(
        oid=OID_INT4RANGE,
        name="int4range",
        element_decode=_int4_decode,
        element_encode=_int4_encode,
    )
    with pytest.raises(ProtocolError, match="text format is unsupported"):
        codec.decode_text(b"[1,2)")
    with pytest.raises(ProtocolError, match="text format is unsupported"):
        codec.encode_text(Range())


@pytest.mark.issue(255)
def test_range_truncated_flags_raises_protocol_error():
    with pytest.raises(ProtocolError, match="missing flags byte"):
        decode_range(b"", _int4_decode)


@pytest.mark.issue(255)
def test_range_truncated_bound_raises_protocol_error():
    wire = b"\x02\x00\x00\x00\x04\x00\x00"  # claims a 4-byte lower bound, only 2 follow
    with pytest.raises(ProtocolError, match="truncated range lower bound"):
        decode_range(wire, _int4_decode)


@pytest.mark.issue(255)
def test_range_trailing_bytes_raise_protocol_error():
    wire = b"\x18\xde\xad"  # fully unbounded but with stray trailing bytes
    with pytest.raises(ProtocolError, match="trailing byte"):
        decode_range(wire, _int4_decode)


@pytest.mark.issue(255)
def test_empty_range_with_trailing_bytes_raises_protocol_error():
    with pytest.raises(ProtocolError, match="trailing byte"):
        decode_range(b"\x01\x00", _int4_decode)


# === ENUM ===================================================================
@pytest.mark.issue(255)
def test_enum_known_vector():
    # An enum value is just its UTF-8 label, identical in binary and text format.
    codec = make_enum_codec(123456, "mood")
    assert codec.decode_binary(b"happy") == "happy"
    assert codec.encode_binary("happy") == b"happy"
    # Multibyte label round-trips.
    assert codec.decode_binary("café".encode()) == "café"


@pytest.mark.issue(255)
def test_enum_codec_metadata():
    codec = make_enum_codec(654321, "status")
    assert codec.oid == 654321
    assert codec.name == "status"
    # Enums are text-on-the-wire, so the driver should not request binary.
    assert codec.prefers_binary is False
    # Binary and text decoders are the same UTF-8 path.
    assert codec.decode_binary is codec.decode_text


@pytest.mark.issue(255)
@given(value=st.text())
def test_enum_round_trip(value):
    codec = make_enum_codec(123456, "mood")
    assert codec.decode_binary(codec.encode_binary(value)) == value
    assert codec.decode_text(codec.encode_text(value)) == value
