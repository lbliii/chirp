"""E2 (#255) — the codec registry hub + the per-column result-decoding plan.

These exercise :func:`build_codec_plan`: a mixed-type ``RowDescription`` must produce one correct
``(bytes | None) -> Any`` decoder per column, SQL NULL must decode to ``None``, an unregistered
OID must hit the fail-soft text/binary fallback (never crash the row path), and a parametric
``int4[]`` column must round-trip through the plan against the element codec resolved from the
registry snapshot.

Live-PostgreSQL parity is deferred to E4/E6 integration; here the wire bytes are produced by the
very codecs the plan resolves (a closed round-trip), plus a hand-built ``int4[]`` vector cited
against the documented binary array layout.
"""

from __future__ import annotations

import datetime as _dt
import uuid as _uuid
from decimal import Decimal

import pytest

from chirp.data.drivers._pelt._codecs import (
    DEFAULT_REGISTRY,
    OID_BOOL,
    OID_INT4,
    OID_TEXT,
    build_codec_plan,
    build_default_registry,
)
from chirp.data.drivers._pelt._codecs_array import OID_ARRAY_INT4
from chirp.data.drivers._pelt._codecs_composite_range_enum import OID_INT4RANGE, Range
from chirp.data.drivers._pelt._codecs_json import OID_JSONB
from chirp.data.drivers._pelt._codecs_numeric import OID_NUMERIC
from chirp.data.drivers._pelt._codecs_temporal import OID_DATE
from chirp.data.drivers._pelt._codecs_uuid_bytea import OID_UUID
from chirp.data.drivers._pelt._messages import DataRow, FieldDescription, RowDescription

# Wire format codes carried in FieldDescription.format_code / Bind.
_FMT_TEXT = 0
_FMT_BINARY = 1


def _field(type_oid: int, *, fmt: int = _FMT_BINARY, name: str = "c") -> FieldDescription:
    """A FieldDescription with only the OID + format_code load-bearing for the plan."""
    return FieldDescription(
        name=name,
        table_oid=0,
        column_attr=0,
        type_oid=type_oid,
        type_size=-1,
        type_modifier=-1,
        format_code=fmt,
    )


def _enc(oid: int, value: object, *, binary: bool = True) -> bytes:
    """Encode ``value`` via the registered codec for ``oid`` — the inverse of what the plan does."""
    codec = DEFAULT_REGISTRY.get(oid)
    assert codec is not None, f"OID {oid} not registered"
    return codec.encode_binary(value) if binary else codec.encode_text(value)


# --- registry hub: E2 families are wired -------------------------------------
@pytest.mark.issue(255)
@pytest.mark.parametrize(
    "oid",
    [
        OID_NUMERIC,  # numeric family
        OID_DATE,  # temporal family
        OID_UUID,  # uuid/bytea family
        OID_JSONB,  # json family
    ],
)
def test_default_registry_wires_e2_leaf_families(oid):
    assert DEFAULT_REGISTRY.get(oid) is not None


@pytest.mark.issue(255)
def test_build_default_registry_is_fail_loud_and_conflict_free():
    # A fresh build must succeed (no two families claiming the same OID) — the fail-loud
    # register() would have raised at build time otherwise.
    reg = build_default_registry()
    snap = reg.snapshot()
    # E1 (9) + numeric (1) + temporal (6) + uuid/bytea (2) + json/jsonb (2) = 20.
    assert len(snap) == 20


# --- mixed-type plan: correct per-column decoder -----------------------------
@pytest.mark.issue(255)
def test_mixed_row_description_decodes_each_column_correctly():
    snap = DEFAULT_REGISTRY.snapshot()
    row_desc = RowDescription(
        fields=(
            _field(OID_INT4, name="i"),
            _field(OID_TEXT, name="t"),
            _field(OID_BOOL, name="b"),
            _field(OID_NUMERIC, name="n"),
            _field(OID_UUID, name="u"),
        )
    )
    plan = build_codec_plan(row_desc, snap)
    assert len(plan) == 5

    u = _uuid.UUID("12345678-1234-5678-1234-567812345678")
    row = DataRow(
        values=(
            _enc(OID_INT4, 42),
            _enc(OID_TEXT, "héllo"),
            _enc(OID_BOOL, True),
            _enc(OID_NUMERIC, Decimal("1.50")),
            _enc(OID_UUID, u),
        )
    )
    decoded = tuple(decode(raw) for decode, raw in zip(plan, row.values, strict=True))
    assert decoded[0] == 42
    assert decoded[1] == "héllo"
    assert decoded[2] is True
    assert decoded[3] == Decimal("1.50")
    assert decoded[4] == u


@pytest.mark.issue(255)
def test_plan_honors_format_code_text_vs_binary():
    snap = DEFAULT_REGISTRY.snapshot()
    # Same OID, two columns: one binary, one text. The plan must pick the matching half.
    row_desc = RowDescription(
        fields=(_field(OID_INT4, fmt=_FMT_BINARY), _field(OID_INT4, fmt=_FMT_TEXT))
    )
    plan = build_codec_plan(row_desc, snap)
    assert plan[0](_enc(OID_INT4, 7, binary=True)) == 7
    assert plan[1](_enc(OID_INT4, 7, binary=False)) == 7
    # And the text decoder really is the text half: it parses ASCII digits, not raw int bytes.
    assert plan[1](b"123") == 123


# --- NULL handling -----------------------------------------------------------
@pytest.mark.issue(255)
def test_null_columns_decode_to_none_regardless_of_type():
    snap = DEFAULT_REGISTRY.snapshot()
    row_desc = RowDescription(
        fields=(_field(OID_INT4), _field(OID_TEXT, fmt=_FMT_TEXT), _field(OID_NUMERIC))
    )
    plan = build_codec_plan(row_desc, snap)
    # A SQL NULL column arrives as None (DataRow value -1-length); every decoder yields None.
    assert plan[0](None) is None
    assert plan[1](None) is None
    assert plan[2](None) is None


# --- unregistered OID: fail-soft fallback ------------------------------------
@pytest.mark.issue(255)
def test_unregistered_binary_oid_falls_back_to_raw_bytes():
    snap = DEFAULT_REGISTRY.snapshot()
    unknown_oid = 999_999  # not in pg_type and definitely not registered
    assert snap.get(unknown_oid) is None
    plan = build_codec_plan(RowDescription(fields=(_field(unknown_oid, fmt=_FMT_BINARY),)), snap)
    raw = b"\xde\xad\xbe\xef"
    # Binary fallback hands the bytes back verbatim — never crashes, never guesses a type.
    assert plan[0](raw) == raw
    assert plan[0](None) is None


@pytest.mark.issue(255)
def test_unregistered_text_oid_falls_back_to_utf8():
    snap = DEFAULT_REGISTRY.snapshot()
    plan = build_codec_plan(RowDescription(fields=(_field(424242, fmt=_FMT_TEXT),)), snap)
    assert plan[0]("naïve".encode()) == "naïve"
    assert plan[0](None) is None


@pytest.mark.issue(255)
def test_unknown_type_does_not_crash_the_row_path():
    # An entire row of unknown types must decode without raising.
    snap = DEFAULT_REGISTRY.snapshot()
    row_desc = RowDescription(
        fields=(_field(700001, fmt=_FMT_BINARY), _field(700002, fmt=_FMT_TEXT))
    )
    plan = build_codec_plan(row_desc, snap)
    row = DataRow(values=(b"\x00\x01", b"plain text"))
    decoded = tuple(decode(raw) for decode, raw in zip(plan, row.values, strict=True))
    assert decoded == (b"\x00\x01", "plain text")


# --- parametric: int4[] resolves its element codec and round-trips -----------
@pytest.mark.issue(255)
def test_int4_array_column_round_trips_through_the_plan():
    snap = DEFAULT_REGISTRY.snapshot()
    plan = build_codec_plan(RowDescription(fields=(_field(OID_ARRAY_INT4),)), snap)

    # Build the wire bytes with the same array encoder the registry would use for _int4.
    from chirp.data.drivers._pelt._codecs_array import encode_array

    int4 = DEFAULT_REGISTRY.get(OID_INT4)
    assert int4 is not None
    wire = encode_array([1, 2, 3], element_oid=OID_INT4, encode_elem=int4.encode_binary)
    assert plan[0](wire) == [1, 2, 3]
    # NULL element inside the array survives the element-codec resolution.
    wire_nulls = encode_array([7, None], element_oid=OID_INT4, encode_elem=int4.encode_binary)
    assert plan[0](wire_nulls) == [7, None]
    # A SQL NULL *array* column is still None.
    assert plan[0](None) is None


@pytest.mark.issue(255)
def test_int4_array_known_binary_vector_decodes_through_the_plan():
    # int4[] {1,2,3}, binary array layout (big-endian int32 fields):
    #   ndim=1, flags=0 (no nulls), element_oid=23 (int4)
    #   dim[0]: length=3, lower_bound=1
    #   elem: len=4 val=1 | len=4 val=2 | len=4 val=3
    wire = bytes.fromhex(
        "00000001"  # ndim = 1
        "00000000"  # flags = 0
        "00000017"  # element_oid = 23 (int4)
        "00000003"  # dim[0] length = 3
        "00000001"  # dim[0] lower_bound = 1
        "00000004"  # elem[0] length = 4
        "00000001"  # elem[0] value = 1
        "00000004"  # elem[1] length = 4
        "00000002"  # elem[1] value = 2
        "00000004"  # elem[2] length = 4
        "00000003"  # elem[2] value = 3
    )
    snap = DEFAULT_REGISTRY.snapshot()
    plan = build_codec_plan(RowDescription(fields=(_field(OID_ARRAY_INT4),)), snap)
    assert plan[0](wire) == [1, 2, 3]


# --- parametric: int4range resolves its element codec and round-trips --------
@pytest.mark.issue(255)
def test_int4range_column_round_trips_through_the_plan():
    snap = DEFAULT_REGISTRY.snapshot()
    plan = build_codec_plan(RowDescription(fields=(_field(OID_INT4RANGE),)), snap)

    from chirp.data.drivers._pelt._codecs_composite_range_enum import encode_range

    int4 = DEFAULT_REGISTRY.get(OID_INT4)
    assert int4 is not None
    rng = Range(lower=1, upper=10, lower_inc=True, upper_inc=False)
    wire = encode_range(rng, int4.encode_binary)
    decoded = plan[0](wire)
    assert decoded == rng
    assert plan[0](None) is None


# --- parametric fallback: array element codec missing → text fallback --------
@pytest.mark.issue(255)
def test_array_with_unresolvable_element_falls_back_not_crashes():
    # A registry stripped of int4 cannot resolve the _int4 element codec; the plan must fall back
    # to the binary raw-bytes lane rather than raising while building or decoding.
    bare = build_default_registry()
    # Build a snapshot that lacks int4 by using a registry where we never registered it: emulate
    # by snapshotting then deleting is impossible (MappingProxyType is read-only), so use a
    # hand-built dict snapshot missing OID_INT4 but keeping the array OID mapping in play.
    snap = {oid: codec for oid, codec in bare.snapshot().items() if oid != OID_INT4}
    plan = build_codec_plan(RowDescription(fields=(_field(OID_ARRAY_INT4),)), snap)
    raw = b"\x00\x00\x00\x00"  # arbitrary bytes; fallback returns them verbatim, no crash
    assert plan[0](raw) == raw
    assert plan[0](None) is None


# --- plan is reusable across rows --------------------------------------------
@pytest.mark.issue(255)
def test_plan_is_a_tuple_of_reusable_per_column_closures():
    snap = DEFAULT_REGISTRY.snapshot()
    plan = build_codec_plan(RowDescription(fields=(_field(OID_INT4), _field(OID_DATE))), snap)
    assert isinstance(plan, tuple)
    # Decode two different rows with the same plan (computed once per result set).
    d1 = _dt.date(2000, 1, 2)
    d2 = _dt.date(1999, 12, 31)
    assert plan[0](_enc(OID_INT4, 5)) == 5
    assert plan[1](_enc(OID_DATE, d1)) == d1
    assert plan[0](_enc(OID_INT4, -5)) == -5
    assert plan[1](_enc(OID_DATE, d2)) == d2
