"""E2 (#255) — the parametric array codec family: nested-list round-trips, NULL handling,
empty arrays, and bit-exact known-vector tests against the documented binary wire layout.

Live-PG parity is deferred to E4/E6 integration; here we assert against the PostgreSQL
binary array format spec directly. A stub int4 element codec (the real ``_int_codec`` from
``_codecs``) exercises the container logic without coupling to any one leaf type.
"""

import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt._codecs import OID_INT4, _int_codec
from chirp.data.drivers._pelt._codecs_array import (
    ARRAY_OID_TO_ELEMENT,
    LEAF_CODECS,
    MAXDIM,
    OID_ARRAY_INT4,
    decode_array,
    encode_array,
    make_array_codec,
)
from chirp.data.drivers._pelt.errors import ProtocolError

# A concrete element codec — reuse the real int4 leaf codec so we test container logic only.
INT4 = _int_codec(OID_INT4, "int4", 4)
DEC = INT4.decode_binary
ENC = INT4.encode_binary

INT4_ARRAY = make_array_codec(
    array_oid=OID_ARRAY_INT4,
    name="_int4",
    element_oid=OID_INT4,
    element_codec=INT4,
)


def _roundtrip(value):
    return decode_array(encode_array(value, element_oid=OID_INT4, encode_elem=ENC), DEC)


# --- hypothesis round-trip property tests -----------------------------------
_int4 = st.integers(min_value=-(2**31), max_value=2**31 - 1)
_int4_or_null = st.one_of(st.none(), _int4)


@pytest.mark.issue(255)
@given(value=st.lists(_int4_or_null))
def test_one_d_round_trip(value):
    assert _roundtrip(value) == value


@pytest.mark.issue(255)
@given(
    rows=st.integers(min_value=0, max_value=5),
    cols=st.integers(min_value=1, max_value=5),
    fill=_int4_or_null,
)
def test_two_d_round_trip(rows, cols, fill):
    # Rectangular rows x cols matrix (PostgreSQL arrays must be rectangular).
    value = [[fill for _ in range(cols)] for _ in range(rows)]
    assert _roundtrip(value) == value


@pytest.mark.issue(255)
@given(value=st.lists(_int4_or_null))
def test_codec_round_trip(value):
    # Exercise the Codec wrapper (binary fns) rather than the bare helpers.
    assert INT4_ARRAY.decode_binary(INT4_ARRAY.encode_binary(value)) == value


# --- empty / NULL edge cases ------------------------------------------------
@pytest.mark.issue(255)
def test_empty_array_round_trip():
    assert _roundtrip([]) == []


@pytest.mark.issue(255)
def test_empty_array_is_zero_dim_header():
    # Empty array: ndim=0, flags=0, element_oid — and nothing else (no dim/element section).
    encoded = encode_array([], element_oid=OID_INT4, encode_elem=ENC)
    assert encoded == struct.pack(">iii", 0, 0, OID_INT4)
    assert len(encoded) == 12


@pytest.mark.issue(255)
def test_empty_nested_array_encodes_canonical_zero_dim_header():
    # PG flattens any zero-element array to the ndim=0 header regardless of nesting depth:
    # [[]] and [[], []] must NOT emit a positive-ndim header with a zero-length axis.
    canonical = struct.pack(">iii", 0, 0, OID_INT4)
    assert encode_array([[]], element_oid=OID_INT4, encode_elem=ENC) == canonical
    assert encode_array([[], []], element_oid=OID_INT4, encode_elem=ENC) == canonical
    assert encode_array([], element_oid=OID_INT4, encode_elem=ENC) == canonical


@pytest.mark.issue(255)
def test_empty_nested_array_round_trips_to_flat_empty():
    # PG flattens empty arrays to []: [[]] -> bytes -> [] (the nesting is intentionally lost).
    assert _roundtrip([[]]) == []
    assert _roundtrip([[], []]) == []
    assert _roundtrip([]) == []


@pytest.mark.issue(255)
def test_array_with_nulls_round_trip():
    value = [1, None, 3, None]
    assert _roundtrip(value) == value


@pytest.mark.issue(255)
def test_all_nulls_round_trip():
    value = [None, None, None]
    assert _roundtrip(value) == value


@pytest.mark.issue(255)
def test_has_nulls_flag_is_set_when_null_present():
    encoded = encode_array([1, None], element_oid=OID_INT4, encode_elem=ENC)
    _ndim, flags, _oid = struct.unpack_from(">iii", encoded, 0)
    assert flags & 1  # bit 0 = has-nulls


@pytest.mark.issue(255)
def test_has_nulls_flag_clear_without_nulls():
    encoded = encode_array([1, 2], element_oid=OID_INT4, encode_elem=ENC)
    _ndim, flags, _oid = struct.unpack_from(">iii", encoded, 0)
    assert flags == 0


@pytest.mark.issue(255)
def test_edge_values_round_trip():
    value = [-(2**31), 0, 2**31 - 1, None]
    assert _roundtrip(value) == value


# --- known binary wire vectors ----------------------------------------------
@pytest.mark.issue(255)
def test_known_vector_int4_array_1d():
    # int4[] = {1,2,3}, layout per PG binary array format:
    #   ndim=1 flags=0 elem_oid=23 | dim_len=3 lower=1 | (len=4,val)*3
    expected = (
        b"\x00\x00\x00\x01"  # ndim = 1
        b"\x00\x00\x00\x00"  # flags = 0 (no nulls)
        b"\x00\x00\x00\x17"  # element_oid = 23 (int4)
        b"\x00\x00\x00\x03"  # dim[0].length = 3
        b"\x00\x00\x00\x01"  # dim[0].lower_bound = 1
        b"\x00\x00\x00\x04\x00\x00\x00\x01"  # len=4, value=1
        b"\x00\x00\x00\x04\x00\x00\x00\x02"  # len=4, value=2
        b"\x00\x00\x00\x04\x00\x00\x00\x03"  # len=4, value=3
    )
    encoded = encode_array([1, 2, 3], element_oid=OID_INT4, encode_elem=ENC)
    assert encoded == expected
    assert decode_array(expected, DEC) == [1, 2, 3]


@pytest.mark.issue(255)
def test_known_vector_int4_array_with_null():
    # int4[] = {7,NULL}: has-nulls flag set; the NULL element is a bare -1 length, no payload.
    expected = (
        b"\x00\x00\x00\x01"  # ndim = 1
        b"\x00\x00\x00\x01"  # flags = 1 (has nulls)
        b"\x00\x00\x00\x17"  # element_oid = 23 (int4)
        b"\x00\x00\x00\x02"  # dim[0].length = 2
        b"\x00\x00\x00\x01"  # dim[0].lower_bound = 1
        b"\x00\x00\x00\x04\x00\x00\x00\x07"  # len=4, value=7
        b"\xff\xff\xff\xff"  # len=-1 → SQL NULL (no payload)
    )
    encoded = encode_array([7, None], element_oid=OID_INT4, encode_elem=ENC)
    assert encoded == expected
    assert decode_array(expected, DEC) == [7, None]


@pytest.mark.issue(255)
def test_known_vector_int4_array_2d():
    # int4[][] = {{1,2},{3,4}}: ndim=2, two dim headers, 4 elements row-major.
    expected = (
        b"\x00\x00\x00\x02"  # ndim = 2
        b"\x00\x00\x00\x00"  # flags = 0
        b"\x00\x00\x00\x17"  # element_oid = 23 (int4)
        b"\x00\x00\x00\x02\x00\x00\x00\x01"  # dim[0]: length=2, lower=1
        b"\x00\x00\x00\x02\x00\x00\x00\x01"  # dim[1]: length=2, lower=1
        b"\x00\x00\x00\x04\x00\x00\x00\x01"  # 1
        b"\x00\x00\x00\x04\x00\x00\x00\x02"  # 2
        b"\x00\x00\x00\x04\x00\x00\x00\x03"  # 3
        b"\x00\x00\x00\x04\x00\x00\x00\x04"  # 4
    )
    encoded = encode_array([[1, 2], [3, 4]], element_oid=OID_INT4, encode_elem=ENC)
    assert encoded == expected
    assert decode_array(expected, DEC) == [[1, 2], [3, 4]]


@pytest.mark.issue(255)
def test_known_vector_empty_array():
    # Empty array: just the 12-byte header with ndim=0.
    expected = b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x17"
    encoded = encode_array([], element_oid=OID_INT4, encode_elem=ENC)
    assert encoded == expected
    assert decode_array(expected, DEC) == []


# --- malformed-payload guards (protocol faults) -----------------------------
@pytest.mark.issue(255)
def test_truncated_header_raises_protocol_error():
    with pytest.raises(ProtocolError, match="truncated array header"):
        decode_array(b"\x00\x00\x00\x01", DEC)


@pytest.mark.issue(255)
def test_truncated_element_payload_raises_protocol_error():
    # Claims a 3-element dim but supplies only a length prefix with no payload.
    bad = (
        b"\x00\x00\x00\x01"  # ndim = 1
        b"\x00\x00\x00\x00"  # flags
        b"\x00\x00\x00\x17"  # element_oid
        b"\x00\x00\x00\x01\x00\x00\x00\x01"  # dim: length=1, lower=1
        b"\x00\x00\x00\x04"  # len=4 but no following 4 bytes
    )
    with pytest.raises(ProtocolError, match="truncated array element payload"):
        decode_array(bad, DEC)


@pytest.mark.issue(255)
def test_negative_ndim_raises_protocol_error():
    bad = struct.pack(">iii", -1, 0, OID_INT4)
    with pytest.raises(ProtocolError, match="invalid array ndim"):
        decode_array(bad, DEC)


@pytest.mark.issue(255)
def test_ndim_over_maxdim_raises_protocol_error():
    # A header claiming ndim=7 (> MAXDIM=6) is impossible on a real server: a protocol fault,
    # rejected at the header before any dimension/element parsing.
    assert MAXDIM == 6
    bad = struct.pack(">iii", MAXDIM + 1, 0, OID_INT4)
    with pytest.raises(ProtocolError, match="exceeds PostgreSQL MAXDIM"):
        decode_array(bad, DEC)


@pytest.mark.issue(255)
def test_hostile_ndim_raises_protocol_error():
    # A garbage ndim (2**31 - 1) must be rejected explicitly, not merely curbed by the
    # per-dimension truncation guard.
    bad = struct.pack(">iii", 2**31 - 1, 0, OID_INT4)
    with pytest.raises(ProtocolError, match="exceeds PostgreSQL MAXDIM"):
        decode_array(bad, DEC)


@pytest.mark.issue(255)
def test_encode_over_maxdim_nesting_raises_value_error():
    # A 7-deep nesting exceeds MAXDIM=6: caller misuse on encode, raised as ValueError.
    deep = [[[[[[[1]]]]]]]  # 7 levels of nesting
    with pytest.raises(ValueError, match="exceeds PostgreSQL MAXDIM"):
        encode_array(deep, element_oid=OID_INT4, encode_elem=ENC)


@pytest.mark.issue(255)
def test_trailing_bytes_after_complete_array_raises_protocol_error():
    # A fully-decodable {1,2} array followed by two stray bytes is a desync, not a [1,2]:
    # the whole buffer must be consumed (mirrors the composite codec's trailing-byte guard).
    bad = encode_array([1, 2], element_oid=OID_INT4, encode_elem=ENC) + b"\x00\x00"
    with pytest.raises(ProtocolError, match="trailing byte"):
        decode_array(bad, DEC)


@pytest.mark.issue(255)
def test_trailing_bytes_after_empty_header_raises_protocol_error():
    # ndim=0 header (12 bytes) is the entire payload; appended bytes signal a framing desync.
    bad = struct.pack(">iii", 0, 0, OID_INT4) + b"\xde\xad"
    with pytest.raises(ProtocolError, match="trailing byte"):
        decode_array(bad, DEC)


# --- caller-misuse guards (ValueError, per frame() policy) ------------------
@pytest.mark.issue(255)
def test_ragged_array_raises_value_error():
    with pytest.raises(ValueError, match="ragged array"):
        encode_array([[1, 2], [3]], element_oid=OID_INT4, encode_elem=ENC)


@pytest.mark.issue(255)
def test_non_list_value_raises_type_error():
    with pytest.raises(TypeError, match="must be a list"):
        encode_array(42, element_oid=OID_INT4, encode_elem=ENC)


# --- family wiring ----------------------------------------------------------
@pytest.mark.issue(255)
def test_leaf_codecs_is_empty_parametric_family():
    assert LEAF_CODECS == ()


@pytest.mark.issue(255)
def test_array_oid_to_element_map():
    assert ARRAY_OID_TO_ELEMENT[OID_ARRAY_INT4] == OID_INT4
    assert ARRAY_OID_TO_ELEMENT[1009] == 25  # _text → text
    assert ARRAY_OID_TO_ELEMENT[1016] == 20  # _int8 → int8
    assert ARRAY_OID_TO_ELEMENT[1000] == 16  # _bool → bool
    assert ARRAY_OID_TO_ELEMENT[1022] == 701  # _float8 → float8
    assert ARRAY_OID_TO_ELEMENT[2951] == 2950  # _uuid → uuid
    assert ARRAY_OID_TO_ELEMENT[1231] == 1700  # _numeric → numeric
    assert ARRAY_OID_TO_ELEMENT[1185] == 1184  # _timestamptz → timestamptz
    assert ARRAY_OID_TO_ELEMENT[1001] == 17  # _bytea → bytea


@pytest.mark.issue(255)
def test_make_array_codec_metadata():
    assert INT4_ARRAY.oid == OID_ARRAY_INT4
    assert INT4_ARRAY.name == "_int4"
    assert INT4_ARRAY.prefers_binary is True
