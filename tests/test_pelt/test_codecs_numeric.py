"""E2 (#255) — exact ``numeric``/``decimal`` ↔ :class:`decimal.Decimal` codec round-trips.

Property tests assert value-exact binary and text round-trips; the explicit known-vector
tests pin the documented PostgreSQL base-10000 wire layout byte-for-byte. NaN / +Inf / -Inf
ride their dedicated sign words. Live-PostgreSQL parity is deferred to the E4/E6 integration
suites; here we encode/decode against the documented ``numeric_send`` / ``numeric_recv``
layout only.
"""

import struct
import threading
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt._codecs_numeric import (
    LEAF_CODECS,
    OID_NUMERIC,
    numeric_codec,
)
from chirp.data.drivers._pelt.errors import ProtocolError

CODEC = numeric_codec()

# Wire layout (header): int16 ndigits, int16 weight, uint16 sign, int16 dscale, then
# ndigits * uint16 base-10000 digit groups. Sign words: 0x0000 pos, 0x4000 neg,
# 0xC000 NaN, 0xD000 +Inf, 0xF000 -Inf.
_HEADER = struct.Struct(">hhHh")
_DIGIT = struct.Struct(">H")


# --- registry surface -------------------------------------------------------
@pytest.mark.issue(255)
def test_leaf_codecs_exports_numeric():
    assert LEAF_CODECS == (CODEC,)
    (codec,) = LEAF_CODECS
    assert codec.oid == OID_NUMERIC == 1700
    assert codec.name == "numeric"
    assert codec.prefers_binary is True


# --- property round-trips ---------------------------------------------------
@pytest.mark.issue(255)
@given(
    value=st.decimals(allow_nan=False, allow_infinity=False, places=None).filter(
        lambda d: d.as_tuple().exponent <= 0  # canonical (no positive exponent) → scale-exact
    )
)
def test_binary_round_trip_value_and_scale(value):
    decoded = CODEC.decode_binary(CODEC.encode_binary(value))
    assert decoded == value
    # For non-positive exponents PostgreSQL preserves the display scale exactly.
    assert decoded.as_tuple().exponent == value.as_tuple().exponent


@pytest.mark.issue(255)
@given(value=st.decimals(allow_nan=False, allow_infinity=False, places=None))
def test_binary_round_trip_value_exact(value):
    # Positive-exponent Decimals (e.g. 1E+10) normalize to trailing-zero integers with
    # dscale=0, exactly as PostgreSQL stores them — value is preserved, scale may collapse.
    decoded = CODEC.decode_binary(CODEC.encode_binary(value))
    assert decoded == value


@pytest.mark.issue(255)
@given(value=st.decimals(allow_nan=False, allow_infinity=False, places=None))
def test_text_round_trip(value):
    decoded = CODEC.decode_text(CODEC.encode_text(value))
    assert decoded == value


@pytest.mark.issue(255)
@given(
    value=st.decimals(
        min_value=Decimal("-1e6"), max_value=Decimal("1e6"), places=4, allow_nan=False
    )
)
def test_fixed_scale_round_trip(value):
    # Fixed 4-decimal-place values exercise the common money/measurement shape and align
    # exactly on a single base-10000 fractional group boundary.
    decoded = CODEC.decode_binary(CODEC.encode_binary(value))
    assert decoded == value
    assert decoded.as_tuple().exponent == value.as_tuple().exponent


# --- special values ---------------------------------------------------------
@pytest.mark.issue(255)
def test_nan_round_trip():
    encoded = CODEC.encode_binary(Decimal("NaN"))
    # ndigits=0, weight=0, sign=0xC000, dscale=0, no digit groups.
    assert encoded == _HEADER.pack(0, 0, 0xC000, 0)
    assert CODEC.decode_binary(encoded).is_nan()


@pytest.mark.issue(255)
def test_positive_infinity_round_trip():
    encoded = CODEC.encode_binary(Decimal("Infinity"))
    assert encoded == _HEADER.pack(0, 0, 0xD000, 0)
    decoded = CODEC.decode_binary(encoded)
    assert decoded.is_infinite()
    assert not decoded.is_signed()


@pytest.mark.issue(255)
def test_negative_infinity_round_trip():
    encoded = CODEC.encode_binary(Decimal("-Infinity"))
    assert encoded == _HEADER.pack(0, 0, 0xF000, 0)
    decoded = CODEC.decode_binary(encoded)
    assert decoded.is_infinite()
    assert decoded.is_signed()


@pytest.mark.issue(255)
def test_nan_text_round_trip():
    assert CODEC.decode_text(CODEC.encode_text(Decimal("NaN"))).is_nan()


# --- known binary vectors (cite the layout in the bytes) --------------------
@pytest.mark.issue(255)
def test_vector_zero():
    # Decimal('0'): ndigits=0, weight=0, sign=0x0000 (pos), dscale=0, no groups.
    #   00 00  00 00  00 00  00 00
    expected = bytes.fromhex("0000000000000000")
    assert CODEC.encode_binary(Decimal("0")) == expected
    assert CODEC.decode_binary(expected) == Decimal("0")


@pytest.mark.issue(255)
def test_vector_one_two_three_four_point_five_six_seven_eight():
    # Decimal('1234.5678'): two base-10000 groups [1234, 5678].
    #   ndigits=2 (00 02), weight=1 (00 01) → first group * 10000^1,
    #   sign=pos (00 00), dscale=4 (00 04),
    #   group0 = 1234 = 0x04D2, group1 = 5678 = 0x162E.
    expected = bytes.fromhex("000200000000000404d2162e")
    assert CODEC.encode_binary(Decimal("1234.5678")) == expected
    decoded = CODEC.decode_binary(expected)
    assert decoded == Decimal("1234.5678")
    assert decoded.as_tuple().exponent == -4  # dscale preserved


@pytest.mark.issue(255)
def test_vector_negative_one():
    # Decimal('-1'): one group [1].
    #   ndigits=1 (00 01), weight=0 (00 00), sign=neg (40 00), dscale=0 (00 00),
    #   group0 = 1 = 0x0001.
    expected = bytes.fromhex("00010000400000000001")
    assert CODEC.encode_binary(Decimal("-1")) == expected
    assert CODEC.decode_binary(expected) == Decimal("-1")


@pytest.mark.issue(255)
def test_vector_one_point_five_zero_preserves_trailing_zero():
    # Decimal('1.50'): groups [1, 5000]; dscale=2 keeps the trailing zero on decode.
    #   ndigits=2 (00 02), weight=0 (00 00), sign=pos (00 00), dscale=2 (00 02),
    #   group0 = 1 = 0x0001, group1 = 5000 = 0x1388.
    expected = bytes.fromhex("000200000000000200011388")
    assert CODEC.encode_binary(Decimal("1.50")) == expected
    decoded = CODEC.decode_binary(expected)
    assert decoded == Decimal("1.50")
    assert str(decoded) == "1.50"  # trailing zero rendered via dscale=2


@pytest.mark.issue(255)
def test_vector_small_fraction():
    # Decimal('0.0001'): one fractional group.
    #   ndigits=1 (00 01), weight=-1 (ff ff) → group * 10000^-1, sign=pos (00 00),
    #   dscale=4 (00 04), group0 = 1 = 0x0001 (i.e. 1 * 10000^-1 = 0.0001).
    expected = bytes.fromhex("0001ffff0000000400 01".replace(" ", ""))
    assert CODEC.encode_binary(Decimal("0.0001")) == expected
    assert CODEC.decode_binary(expected) == Decimal("0.0001")


# --- NULL / empty handling --------------------------------------------------
@pytest.mark.issue(255)
def test_null_is_handled_by_protocol_not_codec():
    # SQL NULL is signalled by a -1 length in DataRow framing; the codec is never invoked.
    # The narrowest valid header (a value of 0) is an 8-byte payload — anything shorter is
    # a desync, not a NULL.
    short = _HEADER.pack(0, 0, 0x0000, 0)[:-1]
    with pytest.raises(ProtocolError, match="too short"):
        CODEC.decode_binary(short)


# --- fail-loud on malformed wire bytes --------------------------------------
@pytest.mark.issue(255)
def test_truncated_digit_groups_raise_protocol_error():
    # Header claims 2 groups but only one group's bytes follow.
    payload = _HEADER.pack(2, 1, 0x0000, 4) + _DIGIT.pack(1234)
    with pytest.raises(ProtocolError, match="truncated"):
        CODEC.decode_binary(payload)


@pytest.mark.issue(255)
def test_invalid_sign_word_raises_protocol_error():
    payload = _HEADER.pack(0, 0, 0x1234, 0)
    with pytest.raises(ProtocolError, match="invalid numeric sign"):
        CODEC.decode_binary(payload)


@pytest.mark.issue(255)
def test_out_of_range_digit_group_raises_protocol_error():
    # A base-10000 group must be < 10000; 0xFFFF (65535) is out of range.
    payload = _HEADER.pack(1, 0, 0x0000, 0) + _DIGIT.pack(0xFFFF)
    with pytest.raises(ProtocolError, match="base-10000 digit group"):
        CODEC.decode_binary(payload)


# --- explicit edge values ---------------------------------------------------
@pytest.mark.issue(255)
@pytest.mark.parametrize(
    "text",
    [
        "0",
        "0.0",
        "-0.0001",
        "9999.9999",
        "1000000",
        "0.0000000001",
        "-123456789.987654321",
        "123456789012345.678901234",
        "999999999999999999999999",
    ],
)
def test_edge_values_round_trip(text):
    value = Decimal(text)
    decoded = CODEC.decode_binary(CODEC.encode_binary(value))
    assert decoded == value
    assert decoded.as_tuple().exponent == value.as_tuple().exponent


# --- high-precision decode (>28 significant digits / large dscale) ----------
# A 30-significant-digit value blows past decimal's default context prec=28. A precision-bounded
# decode (scaleb/quantize) would silently round it to 28 sig digits or raise InvalidOperation;
# the tuple-form reconstruction must stay bit-exact. Hand-built wire vector below.
#
# Decimal('999999999999999999999999999999')  (NUMERIC(30,0), 30 nines):
#   base-10000 groups MSB-first: [99, 9999, 9999, 9999, 9999, 9999, 9999, 9999]
#   (the top group is 99 because 30 = 4*7 + 2). ndigits=8, weight=7 (group0 * 10000^7),
#   sign=pos (00 00), dscale=0 (00 00).
_THIRTY_NINES = Decimal("9" * 30)
_THIRTY_NINES_WIRE = _HEADER.pack(8, 7, 0x0000, 0) + b"".join(
    _DIGIT.pack(g) for g in (99, 9999, 9999, 9999, 9999, 9999, 9999, 9999)
)

# Decimal('0.000...0001') with 40 fractional digits (large dscale, single significant digit):
#   value = 1 * 10**-40; base-10000: weight = -10 (least group at 10000^-10 = 10**-40),
#   ndigits=1, group0 = 1, dscale=40. quantize(10**-40) raises InvalidOperation under prec=28.
_TINY_FRACTION = Decimal("1E-40")
_TINY_FRACTION_WIRE = _HEADER.pack(1, -10, 0x0000, 40) + _DIGIT.pack(1)


@pytest.mark.issue(255)
def test_high_precision_decode_vector_on_import_thread():
    # Sanity: the hand-built vectors decode exactly on the import thread first.
    assert CODEC.decode_binary(_THIRTY_NINES_WIRE) == _THIRTY_NINES
    assert CODEC.decode_binary(_THIRTY_NINES_WIRE).as_tuple() == _THIRTY_NINES.as_tuple()
    assert CODEC.decode_binary(_TINY_FRACTION_WIRE) == _TINY_FRACTION
    assert CODEC.decode_binary(_TINY_FRACTION_WIRE).as_tuple().exponent == -40


@pytest.mark.issue(255)
def test_high_precision_decode_on_worker_thread():
    # The bug this locks in: decimal's context is thread-local, so a worker thread keeps the
    # default prec=28 regardless of any import-time getcontext() mutation. A precision-bounded
    # decode silently rounds the 30-nines value to 28 sig digits and RAISES InvalidOperation on
    # the 40-place fraction. The tuple-form reconstruction must be bit-exact on any thread —
    # pelt is a free-threading-native driver that decodes rows across worker threads (epic E6).
    results: dict[str, object] = {}

    def worker() -> None:
        try:
            results["nines"] = CODEC.decode_binary(_THIRTY_NINES_WIRE)
            results["tiny"] = CODEC.decode_binary(_TINY_FRACTION_WIRE)
        except Exception as exc:  # pragma: no cover - failure is the assertion below
            results["error"] = exc

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert "error" not in results, f"decode raised on worker thread: {results.get('error')!r}"
    assert results["nines"] == _THIRTY_NINES
    # Exact to the digit — not rounded to 28 significant digits.
    assert results["nines"].as_tuple() == _THIRTY_NINES.as_tuple()  # type: ignore[union-attr]
    assert results["tiny"] == _TINY_FRACTION
    assert results["tiny"].as_tuple().exponent == -40  # type: ignore[union-attr]


@pytest.mark.issue(255)
def test_high_precision_round_trip_on_worker_thread():
    # Full encode->decode round-trip on a worker thread for a value far past prec=28, covering
    # both a long integer run and a long fractional run with a large dscale.
    values = [
        Decimal("123456789012345678901234567890.123456789012345"),
        Decimal("-" + "9" * 40 + ".0001"),
        Decimal("9" * 50),
    ]
    results: dict[str, object] = {}

    def worker() -> None:
        try:
            results["decoded"] = [CODEC.decode_binary(CODEC.encode_binary(v)) for v in values]
        except Exception as exc:  # pragma: no cover - failure is the assertion below
            results["error"] = exc

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert "error" not in results, f"round-trip raised on worker thread: {results.get('error')!r}"
    for original, decoded in zip(values, results["decoded"], strict=True):  # type: ignore[arg-type]
        assert decoded == original
        assert decoded.as_tuple().exponent == original.as_tuple().exponent
