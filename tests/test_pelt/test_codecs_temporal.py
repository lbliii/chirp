"""E2 (#255) — temporal codec round-trips + bit-exact PostgreSQL binary wire vectors.

The binary layouts are big-endian, PostgreSQL-epoch (2000-01-01 00:00:00) relative. Each
hardcoded vector cites the layout it asserts; live-PG parity for the full text-format surface
is deferred to E4/E6 integration.
"""

import datetime as dt
import pickle

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt._codecs_temporal import (
    DATE_CODEC,
    INTERVAL_CODEC,
    LEAF_CODECS,
    OID_DATE,
    OID_INTERVAL,
    OID_TIME,
    OID_TIMESTAMP,
    OID_TIMESTAMPTZ,
    OID_TIMETZ,
    TIME_CODEC,
    TIMESTAMP_CODEC,
    TIMESTAMPTZ_CODEC,
    TIMETZ_CODEC,
    Interval,
)
from chirp.data.drivers._pelt.errors import ProtocolError

UTC = dt.UTC


# --- packaging / registry-readiness -----------------------------------------
@pytest.mark.issue(255)
def test_leaf_codecs_cover_every_temporal_oid():
    oids = {c.oid for c in LEAF_CODECS}
    assert oids == {
        OID_DATE,
        OID_TIME,
        OID_TIMESTAMP,
        OID_TIMESTAMPTZ,
        OID_TIMETZ,
        OID_INTERVAL,
    }
    # No duplicate OIDs (the registry would reject them fail-loud).
    assert len(oids) == len(LEAF_CODECS)


@pytest.mark.issue(255)
def test_leaf_codecs_are_registrable():
    from chirp.data.drivers._pelt._codecs import CodecRegistry

    reg = CodecRegistry()
    for codec in LEAF_CODECS:
        reg.register(codec)
    assert reg.get(OID_TIMESTAMP) is TIMESTAMP_CODEC


# --- known binary vectors ---------------------------------------------------
@pytest.mark.issue(255)
def test_date_epoch_is_zero_days():
    # date layout: int32 days since 2000-01-01. 2000-01-01 -> 0.
    assert DATE_CODEC.encode_binary(dt.date(2000, 1, 1)) == b"\x00\x00\x00\x00"
    assert DATE_CODEC.decode_binary(b"\x00\x00\x00\x00") == dt.date(2000, 1, 1)
    # 2000-01-02 -> 1 day.
    assert DATE_CODEC.encode_binary(dt.date(2000, 1, 2)) == b"\x00\x00\x00\x01"
    assert DATE_CODEC.decode_binary(b"\x00\x00\x00\x01") == dt.date(2000, 1, 2)
    # 1999-12-31 -> -1 day (two's complement int32).
    assert DATE_CODEC.encode_binary(dt.date(1999, 12, 31)) == b"\xff\xff\xff\xff"
    assert DATE_CODEC.decode_binary(b"\xff\xff\xff\xff") == dt.date(1999, 12, 31)


@pytest.mark.issue(255)
def test_time_known_vector():
    # time layout: int64 microseconds since midnight.
    # 12:34:56.789000 = (12*3600+34*60+56)*1e6 + 789000 = 45_296_789_000 µs.
    raw = bytes.fromhex("0000000a8be62608")
    value = dt.time(12, 34, 56, 789000)
    assert TIME_CODEC.encode_binary(value) == raw
    assert TIME_CODEC.decode_binary(raw) == value
    # midnight -> 0.
    assert TIME_CODEC.encode_binary(dt.time(0, 0, 0)) == b"\x00" * 8
    assert TIME_CODEC.decode_binary(b"\x00" * 8) == dt.time(0, 0, 0)


@pytest.mark.issue(255)
def test_timestamp_epoch_is_zero_micros():
    # timestamp layout: int64 µs since 2000-01-01 00:00:00 (naive).
    assert TIMESTAMP_CODEC.encode_binary(dt.datetime(2000, 1, 1, 0, 0, 0)) == b"\x00" * 8
    assert TIMESTAMP_CODEC.decode_binary(b"\x00" * 8) == dt.datetime(2000, 1, 1)
    # one second after epoch -> 1_000_000 µs.
    one_sec = (1_000_000).to_bytes(8, "big", signed=True)
    assert TIMESTAMP_CODEC.encode_binary(dt.datetime(2000, 1, 1, 0, 0, 1)) == one_sec
    assert TIMESTAMP_CODEC.decode_binary(one_sec) == dt.datetime(2000, 1, 1, 0, 0, 1)


@pytest.mark.issue(255)
def test_timestamptz_epoch_is_aware_utc():
    # timestamptz layout: int64 µs since 2000-01-01 00:00:00 UTC.
    epoch_utc = dt.datetime(2000, 1, 1, tzinfo=UTC)
    assert TIMESTAMPTZ_CODEC.encode_binary(epoch_utc) == b"\x00" * 8
    decoded = TIMESTAMPTZ_CODEC.decode_binary(b"\x00" * 8)
    assert decoded == epoch_utc
    assert decoded.tzinfo is UTC


@pytest.mark.issue(255)
def test_timetz_known_vector():
    # timetz layout: int64 µs-since-midnight + int32 zone-offset-seconds (west of UTC).
    # 01:02:03 at UTC+1 -> micros=3_723_000_000, zone_secs=-3600 (PG stores west-positive).
    raw = bytes.fromhex("00000000dde878c0") + bytes.fromhex("fffff1f0")
    value = dt.time(1, 2, 3, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    assert TIMETZ_CODEC.encode_binary(value) == raw
    decoded = TIMETZ_CODEC.decode_binary(raw)
    assert decoded.hour == 1
    assert decoded.minute == 2
    assert decoded.second == 3
    assert decoded.utcoffset() == dt.timedelta(hours=1)


@pytest.mark.issue(255)
def test_interval_known_vectors():
    # interval layout: int64 micros + int32 days + int32 months (wire order).
    # 1 month -> micros=0, days=0, months=1.
    raw_month = bytes.fromhex("0000000000000000") + b"\x00\x00\x00\x00" + b"\x00\x00\x00\x01"
    assert INTERVAL_CODEC.encode_binary(Interval(months=1)) == raw_month
    assert INTERVAL_CODEC.decode_binary(raw_month) == Interval(months=1)
    # months==0 decodes to a plain timedelta (2 days + 3 seconds).
    td = dt.timedelta(days=2, seconds=3)
    encoded = INTERVAL_CODEC.encode_binary(td)
    assert (
        encoded
        == (3_000_000).to_bytes(8, "big", signed=True)
        + (2).to_bytes(4, "big", signed=True)
        + b"\x00\x00\x00\x00"
    )
    assert INTERVAL_CODEC.decode_binary(encoded) == td


# --- infinity handling ------------------------------------------------------
@pytest.mark.issue(255)
def test_timestamp_positive_infinity_round_trips():
    # +infinity sentinel: int64 0x7fff_ffff_ffff_ffff -> datetime.max.
    pos_inf = bytes.fromhex("7fffffffffffffff")
    assert TIMESTAMP_CODEC.decode_binary(pos_inf) == dt.datetime.max
    assert TIMESTAMP_CODEC.encode_binary(dt.datetime.max) == pos_inf


@pytest.mark.issue(255)
def test_timestamp_negative_infinity_round_trips():
    # -infinity sentinel: int64 -0x8000_0000_0000_0000 -> datetime.min.
    neg_inf = bytes.fromhex("8000000000000000")
    assert TIMESTAMP_CODEC.decode_binary(neg_inf) == dt.datetime.min
    assert TIMESTAMP_CODEC.encode_binary(dt.datetime.min) == neg_inf


@pytest.mark.issue(255)
def test_timestamptz_infinity_round_trips_aware():
    pos_inf = bytes.fromhex("7fffffffffffffff")
    neg_inf = bytes.fromhex("8000000000000000")
    max_utc = dt.datetime.max.replace(tzinfo=UTC)
    min_utc = dt.datetime.min.replace(tzinfo=UTC)
    assert TIMESTAMPTZ_CODEC.decode_binary(pos_inf) == max_utc
    assert TIMESTAMPTZ_CODEC.decode_binary(neg_inf) == min_utc
    assert TIMESTAMPTZ_CODEC.encode_binary(max_utc) == pos_inf
    assert TIMESTAMPTZ_CODEC.encode_binary(min_utc) == neg_inf


# --- timestamptz tz normalisation -------------------------------------------
@pytest.mark.issue(255)
def test_timestamptz_normalises_offset_to_utc():
    # 2000-01-01 01:00:00+01:00 is the epoch instant -> 0 µs on the wire.
    plus_one = dt.datetime(2000, 1, 1, 1, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    assert TIMESTAMPTZ_CODEC.encode_binary(plus_one) == b"\x00" * 8
    # decode always lands in UTC.
    assert TIMESTAMPTZ_CODEC.decode_binary(b"\x00" * 8) == plus_one


@pytest.mark.issue(255)
def test_timestamptz_naive_assumed_utc():
    naive = dt.datetime(2000, 1, 1, 0, 0, 1)
    assert TIMESTAMPTZ_CODEC.encode_binary(naive) == (1_000_000).to_bytes(8, "big", signed=True)


# --- round-trip property tests ----------------------------------------------
@pytest.mark.issue(255)
@given(value=st.dates(min_value=dt.date(1, 1, 1), max_value=dt.date(9999, 12, 31)))
def test_date_binary_round_trip(value):
    assert DATE_CODEC.decode_binary(DATE_CODEC.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(value=st.dates(min_value=dt.date(1, 1, 1), max_value=dt.date(9999, 12, 31)))
def test_date_text_round_trip(value):
    assert DATE_CODEC.decode_text(DATE_CODEC.encode_text(value)) == value


@pytest.mark.issue(255)
@given(value=st.times())
def test_time_binary_round_trip(value):
    assert TIME_CODEC.decode_binary(TIME_CODEC.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(value=st.times())
def test_time_text_round_trip(value):
    assert TIME_CODEC.decode_text(TIME_CODEC.encode_text(value)) == value


@pytest.mark.issue(255)
@given(
    value=st.datetimes(
        min_value=dt.datetime(1, 1, 2),
        max_value=dt.datetime(9999, 12, 30),
    )
)
def test_timestamp_binary_round_trip(value):
    assert TIMESTAMP_CODEC.decode_binary(TIMESTAMP_CODEC.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(
    value=st.datetimes(
        min_value=dt.datetime(1, 1, 2),
        max_value=dt.datetime(9999, 12, 30),
    )
)
def test_timestamp_text_round_trip(value):
    assert TIMESTAMP_CODEC.decode_text(TIMESTAMP_CODEC.encode_text(value)) == value


@pytest.mark.issue(255)
@given(
    value=st.datetimes(
        min_value=dt.datetime(1, 1, 2),
        max_value=dt.datetime(9999, 12, 30),
        timezones=st.just(UTC),
    )
)
def test_timestamptz_binary_round_trip(value):
    assert TIMESTAMPTZ_CODEC.decode_binary(TIMESTAMPTZ_CODEC.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(
    micros=st.integers(min_value=0, max_value=86_400 * 1_000_000 - 1),
    offset_minutes=st.integers(min_value=-(23 * 60 + 59), max_value=23 * 60 + 59),
)
def test_timetz_binary_round_trip(micros, offset_minutes):
    # Build an aware time from raw micros so we cover the full domain (incl. sub-second).
    secs, micro = divmod(micros, 1_000_000)
    minutes, second = divmod(secs, 60)
    hour, minute = divmod(minutes, 60)
    tz = dt.timezone(dt.timedelta(minutes=offset_minutes))
    value = dt.time(hour, minute, second, micro, tzinfo=tz)
    decoded = TIMETZ_CODEC.decode_binary(TIMETZ_CODEC.encode_binary(value))
    assert decoded.hour == value.hour
    assert decoded.minute == value.minute
    assert decoded.second == value.second
    assert decoded.microsecond == value.microsecond
    assert decoded.utcoffset() == value.utcoffset()


@pytest.mark.issue(255)
@given(
    months=st.integers(min_value=-100_000, max_value=100_000),
    days=st.integers(min_value=-100_000, max_value=100_000),
    micros=st.integers(min_value=-(10**15), max_value=10**15),
)
def test_interval_binary_round_trip(months, days, micros):
    value = Interval(months=months, days=days, microseconds=micros)
    decoded = INTERVAL_CODEC.decode_binary(INTERVAL_CODEC.encode_binary(value))
    if months == 0:
        # months-free intervals collapse to timedelta; compare via the canonical triple.
        assert isinstance(decoded, dt.timedelta)
        td = dt.timedelta(days=days, microseconds=micros)
        assert decoded == td
    else:
        assert decoded == value


@pytest.mark.issue(255)
@given(
    days=st.integers(min_value=-100_000, max_value=100_000),
    seconds=st.integers(min_value=0, max_value=86_399),
    micros=st.integers(min_value=0, max_value=999_999),
)
def test_interval_timedelta_round_trip(days, seconds, micros):
    td = dt.timedelta(days=days, seconds=seconds, microseconds=micros)
    decoded = INTERVAL_CODEC.decode_binary(INTERVAL_CODEC.encode_binary(td))
    assert decoded == td


# --- fail-loud behaviour ----------------------------------------------------
@pytest.mark.issue(255)
def test_time_decode_rejects_out_of_range_micros():
    # > 1 day of micros is not a valid time-of-day.
    bad = (86_400 * 1_000_000).to_bytes(8, "big", signed=True)
    with pytest.raises(ProtocolError, match="out of range"):
        TIME_CODEC.decode_binary(bad)


@pytest.mark.issue(255)
def test_timetz_encode_requires_aware_time():
    with pytest.raises(ValueError, match="aware time"):
        TIMETZ_CODEC.encode_binary(dt.time(1, 2, 3))


@pytest.mark.issue(255)
def test_date_encode_rejects_datetime():
    # datetime IS-A date; the date codec must reject it to avoid a silent truncation.
    with pytest.raises(TypeError, match=r"datetime\.date"):
        DATE_CODEC.encode_binary(dt.datetime(2000, 1, 1))


@pytest.mark.issue(255)
def test_interval_encode_rejects_wrong_type():
    with pytest.raises(TypeError, match="timedelta or Interval"):
        INTERVAL_CODEC.encode_binary("nope")


@pytest.mark.issue(255)
def test_interval_text_decode_is_deferred():
    with pytest.raises(ProtocolError, match="deferred to E4/E6"):
        INTERVAL_CODEC.decode_text(b"1 mon")


@pytest.mark.issue(255)
def test_interval_to_timedelta_approximates_months():
    assert Interval(months=1).to_timedelta() == dt.timedelta(days=30)
    assert Interval(months=2, days=1, microseconds=5).to_timedelta() == dt.timedelta(
        days=61, microseconds=5
    )


# --- malformed-length binary columns (fail-loud, coded) ---------------------
# A truncated/garbled column must raise pelt's ProtocolError (a PELT_* code), never a raw
# struct.error: an uncoded stdlib exception would leak across the driver boundary
# unpicklable-as-PeltError and without a code or hint. Each codec's binary column is a fixed
# width: date=4, time/timestamp/timestamptz=8, timetz=12, interval=16 bytes.
_FIXED_WIDTH_BINARY_DECODERS = [
    (DATE_CODEC, "date", 4),
    (TIME_CODEC, "time", 8),
    (TIMESTAMP_CODEC, "timestamp", 8),
    (TIMESTAMPTZ_CODEC, "timestamptz", 8),
    (TIMETZ_CODEC, "timetz", 12),
    (INTERVAL_CODEC, "interval", 16),
]


@pytest.mark.issue(255)
@pytest.mark.parametrize(("codec", "kind", "size"), _FIXED_WIDTH_BINARY_DECODERS)
def test_binary_decode_rejects_short_column(codec, kind, size):
    # One byte short of the fixed width: would raise a raw struct.error without the guard.
    with pytest.raises(ProtocolError, match=rf"{kind} binary value must be {size} bytes"):
        codec.decode_binary(b"\x00" * (size - 1))


@pytest.mark.issue(255)
@pytest.mark.parametrize(("codec", "kind", "size"), _FIXED_WIDTH_BINARY_DECODERS)
def test_binary_decode_rejects_long_column(codec, kind, size):
    # One byte too long: struct.unpack is exact-width, so a trailing byte is also a desync.
    with pytest.raises(ProtocolError, match=rf"{kind} binary value must be {size} bytes"):
        codec.decode_binary(b"\x00" * (size + 1))


@pytest.mark.issue(255)
@pytest.mark.parametrize(("codec", "kind", "size"), _FIXED_WIDTH_BINARY_DECODERS)
def test_binary_decode_rejects_empty_column(codec, kind, size):
    # An empty (zero-length) column is the degenerate truncation case.
    with pytest.raises(ProtocolError, match=rf"{kind} binary value must be {size} bytes, got 0"):
        codec.decode_binary(b"")


@pytest.mark.issue(255)
def test_malformed_column_error_is_coded_and_picklable():
    # The fault must carry a PELT_* code + an actionable hint and survive pickling — a raw
    # struct.error would do none of these (AGENTS.md non-negotiable).
    with pytest.raises(ProtocolError) as excinfo:
        TIMESTAMP_CODEC.decode_binary(b"\x00\x00\x00")
    err = excinfo.value
    assert err.code == "PELT_PROTO_DESYNC"
    assert err.hint is not None
    assert "desync" in err.hint
    restored = pickle.loads(pickle.dumps(err))  # noqa: S301 — round-tripping our own errors
    assert restored.code == err.code
    assert restored.hint == err.hint
    assert str(restored) == str(err)
