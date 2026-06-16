"""E2 temporal codecs — date / time / timestamp / interval.

PostgreSQL stores every temporal value relative to its own epoch,
**2000-01-01 00:00:00**, not the Unix epoch. The binary wire layouts are fixed-width
big-endian integers (no length-prefix here — these codecs see the *column* bytes the
framer already sliced out of a :class:`~._messages.DataRow`):

============  ===========================================================  ===================
OID           binary layout                                                Python type
============  ===========================================================  ===================
date 1082     ``int32`` days since 2000-01-01                              :class:`datetime.date`
time 1083     ``int64`` microseconds since midnight                        :class:`datetime.time`
timestamp     ``int64`` microseconds since 2000-01-01 00:00:00 (no tz)     naive :class:`datetime.datetime`
1114
timestamptz   ``int64`` microseconds since 2000-01-01 00:00:00 UTC         aware :class:`datetime.datetime` (UTC)
1184
timetz 1266   ``int64`` micros since midnight + ``int32`` zone-offset secs  aware :class:`datetime.time`
interval      ``int64`` micros + ``int32`` days + ``int32`` months         :class:`datetime.timedelta` or :class:`Interval`
1186
============  ===========================================================  ===================

**Infinity.** ``timestamp`` / ``timestamptz`` reserve the two extreme ``int64`` values for
``±infinity``: ``0x7fff_ffff_ffff_ffff`` is ``+infinity`` and ``-0x8000_0000_0000_0000`` is
``-infinity``. Python's :class:`datetime.datetime` cannot represent an unbounded instant, so
pelt maps them to :attr:`datetime.datetime.max` / :attr:`datetime.datetime.min` (the saturating
sentinels asyncpg also offers via its ``Infinity`` flag). The mapping is **bijective on the
wire** — encoding ``datetime.max`` / ``datetime.min`` re-emits the infinity ints — so a
round-trip through these codecs is lossless. ``timestamptz`` returns the aware UTC analogues
(:attr:`datetime.datetime.max`/``min`` re-tagged with :data:`datetime.timezone.utc`).

**Interval.** PostgreSQL's interval has three independent fields (months, days, micros) because
a month is not a fixed number of days. :class:`datetime.timedelta` can only carry days+micros,
so a months-bearing interval is decoded to a small frozen :class:`Interval` value object that
keeps all three fields; a months-free interval decodes to a plain :class:`datetime.timedelta`
for ergonomics (this matches asyncpg, which returns ``timedelta`` whenever ``months == 0``).
:func:`Interval.to_timedelta` is offered for callers that accept the "1 month == 30 days"
approximation explicitly.

Text codecs parse/format the ISO-ish forms PostgreSQL emits (``2000-01-01``,
``12:34:56.789``, ``2000-01-01 12:34:56.789+00``, ``P…``-free ``H:M:S`` intervals); they are a
fallback for servers that hand back the text format and are intentionally narrower than the
binary path. Live-PG parity for the full text-format surface (e.g. ``BC`` eras, non-ISO
``DateStyle`` settings) is deferred to E4/E6 integration.

Faults raise pelt's :class:`~chirp.data.drivers._pelt.errors.ProtocolError` (a ``PELT_*``
code + hint), never a bare exception: every binary decoder length-guards its fixed-width
column before :meth:`struct.Struct.unpack`, so a truncated/garbled column is reported as the
malformed-wire desync it is rather than leaking an uncoded :class:`struct.error` across the
driver boundary. ``TypeError`` / ``ValueError`` are reserved for programmer misuse of an
*encode* path (wrong Python type, naive ``timetz``), mirroring ``_builder.frame()``.

This module is sans-I/O: stdlib only (``struct``, ``datetime``), no socket, no anyio.
"""

from __future__ import annotations

import datetime as _dt
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chirp.data.drivers._pelt._codecs import Codec
from chirp.data.drivers._pelt.errors import ProtocolError

if TYPE_CHECKING:
    from collections.abc import Callable

# --- temporal type OIDs (from pg_type.dat) ----------------------------------
OID_DATE = 1082
OID_TIME = 1083
OID_TIMESTAMP = 1114
OID_TIMESTAMPTZ = 1184
OID_INTERVAL = 1186
OID_TIMETZ = 1266

# --- packers (big-endian, signed) -------------------------------------------
_PACK_INT4 = struct.Struct(">i")
_PACK_INT8 = struct.Struct(">q")
# timetz = int64 micros-since-midnight + int32 zone-offset-seconds.
_PACK_TIMETZ = struct.Struct(">qi")
# interval = int64 micros + int32 days + int32 months (in that wire order).
_PACK_INTERVAL = struct.Struct(">qii")

# --- epochs / scale constants -----------------------------------------------
_PG_EPOCH_DATE = _dt.date(2000, 1, 1)
_PG_EPOCH_NAIVE = _dt.datetime(2000, 1, 1)
_PG_EPOCH_UTC = _dt.datetime(2000, 1, 1, tzinfo=_dt.UTC)
_USECS_PER_SEC = 1_000_000
_USECS_PER_DAY = 86_400 * _USECS_PER_SEC

# Reserved int64 sentinels the backend sends for ±infinity timestamps.
_PG_TS_POS_INF = 0x7FFF_FFFF_FFFF_FFFF
_PG_TS_NEG_INF = -0x8000_0000_0000_0000

# datetime.max/min carry microsecond components; precompute the micro-offsets from the PG
# epoch so encode is a pure integer compare (no datetime arithmetic on the hot path).
_DT_MAX_NAIVE = _dt.datetime.max  # 9999-12-31 23:59:59.999999
_DT_MIN_NAIVE = _dt.datetime.min  # 0001-01-01 00:00:00
_DT_MAX_UTC = _DT_MAX_NAIVE.replace(tzinfo=_dt.UTC)
_DT_MIN_UTC = _DT_MIN_NAIVE.replace(tzinfo=_dt.UTC)


# --- interval value object --------------------------------------------------
@dataclass(frozen=True, slots=True)
class Interval:
    """A PostgreSQL ``interval`` with its three independent fields preserved.

    PostgreSQL keeps ``months``, ``days`` and ``microseconds`` separately because a month and
    a day are not fixed durations; collapsing them loses information. A months-free interval
    decodes to a plain :class:`datetime.timedelta` instead — :class:`Interval` is only used
    when ``months != 0``.
    """

    months: int = 0
    days: int = 0
    microseconds: int = 0

    def to_timedelta(self) -> _dt.timedelta:
        """Approximate this interval as a :class:`datetime.timedelta`, treating one month as
        30 days (PostgreSQL's own ``justify_interval`` convention). Lossy for ``months != 0`` —
        callers opt in explicitly."""
        return _dt.timedelta(days=self.months * 30 + self.days, microseconds=self.microseconds)


def _interval_to_micros_days_months(value: Any) -> tuple[int, int, int]:
    """Normalise a :class:`datetime.timedelta` or :class:`Interval` to the wire triple."""
    if isinstance(value, Interval):
        return (value.microseconds, value.days, value.months)
    if isinstance(value, _dt.timedelta):
        # timedelta has no months; carry its whole-day part as `days`, the remainder as micros.
        micros = value.seconds * _USECS_PER_SEC + value.microseconds
        return (micros, value.days, 0)
    msg = f"interval codec expects timedelta or Interval, got {type(value).__name__}"
    raise TypeError(msg)


# --- binary decode/encode helpers -------------------------------------------
def _checked_unpack(packer: struct.Struct, kind: str, data: bytes) -> tuple[Any, ...]:
    """Length-guard a fixed-width column before :meth:`struct.Struct.unpack`.

    A short/long column is the malformed-wire desync case :class:`ProtocolError` exists to
    signal — a raw :class:`struct.error` is an uncoded stdlib exception that would leak across
    the driver boundary unpicklable-as-:class:`PeltError` and without a ``PELT_*`` code or hint.
    Mirrors the explicit ``len()`` check + hint in the ``uuid`` / ``numeric`` sibling codecs.
    """
    if len(data) != packer.size:
        msg = f"{kind} binary value must be {packer.size} bytes, got {len(data)}"
        raise ProtocolError(
            msg, hint="the backend sent a malformed/truncated column; the stream may have desynced"
        )
    return packer.unpack(data)


def _decode_date_binary(data: bytes) -> _dt.date:
    days = _checked_unpack(_PACK_INT4, "date", data)[0]
    try:
        return _PG_EPOCH_DATE + _dt.timedelta(days=days)
    except (OverflowError, ValueError) as exc:
        msg = f"date out of range: {days} days from 2000-01-01"
        raise ProtocolError(msg) from exc


def _encode_date_binary(value: Any) -> bytes:
    if not isinstance(value, _dt.date) or isinstance(value, _dt.datetime):
        msg = f"date codec expects datetime.date, got {type(value).__name__}"
        raise TypeError(msg)
    return _PACK_INT4.pack((value - _PG_EPOCH_DATE).days)


def _decode_time_binary(data: bytes) -> _dt.time:
    micros = _checked_unpack(_PACK_INT8, "time", data)[0]
    return _micros_to_time(micros)


def _encode_time_binary(value: Any) -> bytes:
    if not isinstance(value, _dt.time):
        msg = f"time codec expects datetime.time, got {type(value).__name__}"
        raise TypeError(msg)
    return _PACK_INT8.pack(_time_to_micros(value))


def _decode_timestamp_binary(data: bytes) -> _dt.datetime:
    micros = _checked_unpack(_PACK_INT8, "timestamp", data)[0]
    if micros == _PG_TS_POS_INF:
        return _DT_MAX_NAIVE
    if micros == _PG_TS_NEG_INF:
        return _DT_MIN_NAIVE
    try:
        return _PG_EPOCH_NAIVE + _dt.timedelta(microseconds=micros)
    except (OverflowError, ValueError) as exc:
        msg = f"timestamp out of range: {micros} µs from 2000-01-01"
        raise ProtocolError(msg) from exc


def _encode_timestamp_binary(value: Any) -> bytes:
    if not isinstance(value, _dt.datetime):
        msg = f"timestamp codec expects datetime.datetime, got {type(value).__name__}"
        raise TypeError(msg)
    if value == _DT_MAX_NAIVE:
        return _PACK_INT8.pack(_PG_TS_POS_INF)
    if value == _DT_MIN_NAIVE:
        return _PACK_INT8.pack(_PG_TS_NEG_INF)
    delta = value.replace(tzinfo=None) - _PG_EPOCH_NAIVE
    return _PACK_INT8.pack(_timedelta_to_micros(delta))


def _decode_timestamptz_binary(data: bytes) -> _dt.datetime:
    micros = _checked_unpack(_PACK_INT8, "timestamptz", data)[0]
    if micros == _PG_TS_POS_INF:
        return _DT_MAX_UTC
    if micros == _PG_TS_NEG_INF:
        return _DT_MIN_UTC
    try:
        return _PG_EPOCH_UTC + _dt.timedelta(microseconds=micros)
    except (OverflowError, ValueError) as exc:
        msg = f"timestamptz out of range: {micros} µs from 2000-01-01 UTC"
        raise ProtocolError(msg) from exc


def _encode_timestamptz_binary(value: Any) -> bytes:
    if not isinstance(value, _dt.datetime):
        msg = f"timestamptz codec expects datetime.datetime, got {type(value).__name__}"
        raise TypeError(msg)
    if value == _DT_MAX_UTC:
        return _PACK_INT8.pack(_PG_TS_POS_INF)
    if value == _DT_MIN_UTC:
        return _PACK_INT8.pack(_PG_TS_NEG_INF)
    # Naive datetimes are assumed UTC (PostgreSQL stores timestamptz normalised to UTC).
    aware = value.replace(tzinfo=_dt.UTC) if value.tzinfo is None else value.astimezone(_dt.UTC)
    delta = aware - _PG_EPOCH_UTC
    return _PACK_INT8.pack(_timedelta_to_micros(delta))


def _decode_timetz_binary(data: bytes) -> _dt.time:
    micros, zone_secs = _checked_unpack(_PACK_TIMETZ, "timetz", data)
    # PostgreSQL stores the zone as seconds *west* of UTC (POSIX sign); Python's
    # timezone(timedelta) is seconds *east*, so negate.
    tz = _dt.timezone(_dt.timedelta(seconds=-zone_secs))
    return _micros_to_time(micros, tz)


def _encode_timetz_binary(value: Any) -> bytes:
    if not isinstance(value, _dt.time):
        msg = f"timetz codec expects datetime.time, got {type(value).__name__}"
        raise TypeError(msg)
    offset = value.utcoffset()
    if offset is None:
        msg = "timetz codec requires an aware time (tzinfo set)"
        raise ValueError(msg)
    zone_secs = -int(offset.total_seconds())  # back to seconds-west-of-UTC
    return _PACK_TIMETZ.pack(_time_to_micros(value), zone_secs)


def _decode_interval_binary(data: bytes) -> _dt.timedelta | Interval:
    micros, days, months = _checked_unpack(_PACK_INTERVAL, "interval", data)
    if months == 0:
        return _dt.timedelta(days=days, microseconds=micros)
    return Interval(months=months, days=days, microseconds=micros)


def _encode_interval_binary(value: Any) -> bytes:
    micros, days, months = _interval_to_micros_days_months(value)
    return _PACK_INTERVAL.pack(micros, days, months)


# --- shared scalar helpers --------------------------------------------------
def _timedelta_to_micros(delta: _dt.timedelta) -> int:
    return (delta.days * _USECS_PER_DAY) + (delta.seconds * _USECS_PER_SEC) + delta.microseconds


def _micros_to_time(micros: int, tz: _dt.tzinfo | None = None) -> _dt.time:
    if micros < 0 or micros >= _USECS_PER_DAY:
        msg = f"time-of-day out of range: {micros} µs since midnight"
        raise ProtocolError(msg)
    secs, micro = divmod(micros, _USECS_PER_SEC)
    minutes, second = divmod(secs, 60)
    hour, minute = divmod(minutes, 60)
    return _dt.time(hour, minute, second, micro, tzinfo=tz)


def _time_to_micros(value: _dt.time) -> int:
    return (
        value.hour * 3600 + value.minute * 60 + value.second
    ) * _USECS_PER_SEC + value.microsecond


# --- text decode/encode helpers ---------------------------------------------
def _decode_date_text(data: bytes) -> _dt.date:
    return _dt.date.fromisoformat(data.decode("ascii"))


def _encode_date_text(value: Any) -> bytes:
    return value.isoformat().encode("ascii")


def _decode_time_text(data: bytes) -> _dt.time:
    return _dt.time.fromisoformat(data.decode("ascii"))


def _encode_time_text(value: Any) -> bytes:
    return value.isoformat().encode("ascii")


def _decode_timestamp_text(data: bytes) -> _dt.datetime:
    # PostgreSQL uses a space separator; datetime.fromisoformat (3.11+) accepts it.
    return _dt.datetime.fromisoformat(data.decode("ascii"))


def _encode_timestamp_text(value: Any) -> bytes:
    return value.isoformat(sep=" ").encode("ascii")


def _decode_timetz_text(data: bytes) -> _dt.time:
    return _dt.time.fromisoformat(data.decode("ascii"))


def _encode_timetz_text(value: Any) -> bytes:
    return value.isoformat().encode("ascii")


def _decode_interval_text(data: bytes) -> _dt.timedelta | Interval:
    # Text intervals carry the same three-field shape behind a verbose grammar
    # ("1 mon 2 days 03:04:05"); a faithful text parser is deferred to E4/E6 integration where
    # a live server can validate every DateStyle. Until then we decline rather than guess.
    msg = "interval text-format decode is deferred to E4/E6 integration; request binary format"
    raise ProtocolError(msg)


def _encode_interval_text(value: Any) -> bytes:
    micros, days, months = _interval_to_micros_days_months(value)
    secs, micro = divmod(micros, _USECS_PER_SEC)
    return f"{months} mon {days} days {secs} secs {micro} micros".encode("ascii")


# --- codec constructors -----------------------------------------------------
def _temporal_codec(
    oid: int,
    name: str,
    decode_binary: Callable[[bytes], Any],
    encode_binary: Callable[[Any], bytes],
    decode_text: Callable[[bytes], Any],
    encode_text: Callable[[Any], bytes],
) -> Codec:
    return Codec(
        oid=oid,
        name=name,
        decode_binary=decode_binary,
        decode_text=decode_text,
        encode_binary=encode_binary,
        encode_text=encode_text,
    )


DATE_CODEC = _temporal_codec(
    OID_DATE, "date", _decode_date_binary, _encode_date_binary, _decode_date_text, _encode_date_text
)
TIME_CODEC = _temporal_codec(
    OID_TIME, "time", _decode_time_binary, _encode_time_binary, _decode_time_text, _encode_time_text
)
TIMESTAMP_CODEC = _temporal_codec(
    OID_TIMESTAMP,
    "timestamp",
    _decode_timestamp_binary,
    _encode_timestamp_binary,
    _decode_timestamp_text,
    _encode_timestamp_text,
)
TIMESTAMPTZ_CODEC = _temporal_codec(
    OID_TIMESTAMPTZ,
    "timestamptz",
    _decode_timestamptz_binary,
    _encode_timestamptz_binary,
    _decode_timestamp_text,
    _encode_timestamp_text,
)
TIMETZ_CODEC = _temporal_codec(
    OID_TIMETZ,
    "timetz",
    _decode_timetz_binary,
    _encode_timetz_binary,
    _decode_timetz_text,
    _encode_timetz_text,
)
INTERVAL_CODEC = _temporal_codec(
    OID_INTERVAL,
    "interval",
    _decode_interval_binary,
    _encode_interval_binary,
    _decode_interval_text,
    _encode_interval_text,
)


# Every non-parametric temporal codec, ready for the registry to wire uniformly.
LEAF_CODECS: tuple[Codec, ...] = (
    DATE_CODEC,
    TIME_CODEC,
    TIMESTAMP_CODEC,
    TIMESTAMPTZ_CODEC,
    TIMETZ_CODEC,
    INTERVAL_CODEC,
)
