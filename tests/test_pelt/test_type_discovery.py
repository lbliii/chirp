"""Issue #695: dynamic PostgreSQL type discovery and negotiated result formats."""

import pytest

from chirp.data.drivers._pelt._codecs import (
    OID_INT4,
    OID_TEXT,
    build_codec_plan,
    build_default_registry,
    result_format_codes,
    with_result_formats,
)
from chirp.data.drivers._pelt._codecs_composite_range_enum import Range
from chirp.data.drivers._pelt._messages import FieldDescription, RowDescription
from chirp.data.drivers._pelt._type_discovery import (
    build_type_catalog_query,
    parse_type_catalog_rows,
    register_type_codecs,
)
from chirp.data.drivers._pelt.errors import ProtocolError

ENUM_OID = 910_001
ENUM_ARRAY_OID = 910_002
COMPOSITE_OID = 910_003
RANGE_OID = 910_004
NON_ARRAY_SUBSCRIPT_OID = 910_005
UNKNOWN_OID = 919_999


def _catalog_row(
    oid: int,
    name: str,
    kind: str,
    *,
    element_oid: int = 0,
    range_subtype_oid: int = 0,
    attribute_number: int = 0,
    attribute_type_oid: int = 0,
) -> dict[str, str]:
    return {
        "type_oid": str(oid),
        "type_name": name,
        "type_kind": kind,
        "element_oid": str(element_oid),
        "range_subtype_oid": str(range_subtype_oid),
        "attribute_number": str(attribute_number),
        "attribute_type_oid": str(attribute_type_oid),
    }


def _field(name: str, oid: int) -> FieldDescription:
    return FieldDescription(
        name=name,
        table_oid=0,
        column_attr=0,
        type_oid=oid,
        type_size=-1,
        type_modifier=-1,
        format_code=0,
    )


def _metadata_rows() -> list[dict[str, str]]:
    return [
        _catalog_row(ENUM_OID, "public.mood", "e"),
        _catalog_row(
            ENUM_ARRAY_OID,
            "public._mood",
            "a",
            element_oid=ENUM_OID,
        ),
        _catalog_row(
            COMPOSITE_OID,
            "public.card",
            "c",
            attribute_number=1,
            attribute_type_oid=OID_INT4,
        ),
        _catalog_row(
            COMPOSITE_OID,
            "public.card",
            "c",
            attribute_number=2,
            attribute_type_oid=ENUM_OID,
        ),
        _catalog_row(
            RANGE_OID,
            "public.mood_range",
            "r",
            range_subtype_oid=ENUM_OID,
        ),
        _catalog_row(
            NON_ARRAY_SUBSCRIPT_OID,
            "public.special_subscript",
            "b",
            element_oid=ENUM_OID,
        ),
    ]


@pytest.mark.issue(695)
def test_catalog_query_is_deterministic_schema_qualified_and_numeric_only() -> None:
    query = build_type_catalog_query((COMPOSITE_OID, ENUM_OID, COMPOSITE_OID))

    assert "FROM pg_catalog.pg_type" in query
    assert "JOIN pg_catalog.pg_namespace" in query
    assert "LEFT JOIN pg_catalog.pg_attribute" in query
    assert f"IN ({ENUM_OID}, {COMPOSITE_OID})" in query
    with pytest.raises(ValueError, match="at least one"):
        build_type_catalog_query(())
    with pytest.raises(ValueError, match=r"1\.\.4294967295"):
        build_type_catalog_query((0,))


@pytest.mark.issue(695)
def test_catalog_rows_build_dynamic_enum_array_composite_and_range_codecs() -> None:
    registry = build_default_registry()
    metadata = parse_type_catalog_rows(_metadata_rows())

    registered = register_type_codecs(registry, tuple(reversed(metadata)))

    assert registered == (ENUM_OID, ENUM_ARRAY_OID, COMPOSITE_OID, RANGE_OID)
    assert next(item for item in metadata if item.oid == COMPOSITE_OID).field_oids == (
        OID_INT4,
        ENUM_OID,
    )
    assert next(item for item in metadata if item.oid == ENUM_ARRAY_OID).dependencies == (ENUM_OID,)
    assert next(item for item in metadata if item.oid == NON_ARRAY_SUBSCRIPT_OID).dependencies == ()

    snapshot = registry.snapshot()
    assert snapshot.get(NON_ARRAY_SUBSCRIPT_OID) is None
    declared = RowDescription(
        fields=(
            _field("integer", OID_INT4),
            _field("text", OID_TEXT),
            _field("mood", ENUM_OID),
            _field("moods", ENUM_ARRAY_OID),
            _field("card", COMPOSITE_OID),
            _field("mood_span", RANGE_OID),
            _field("opaque", UNKNOWN_OID),
        )
    )
    formats = result_format_codes(declared, snapshot)
    execution = with_result_formats(declared, formats)
    plan = build_codec_plan(execution, snapshot)

    enum_array = snapshot[ENUM_ARRAY_OID]
    composite = snapshot[COMPOSITE_OID]
    mood_range = snapshot[RANGE_OID]
    integer = snapshot[OID_INT4]
    expected_range = Range("happy", "sad", lower_inc=True)
    raw = (
        integer.encode_binary(7),
        b"plain",
        b"happy",
        enum_array.encode_binary(["happy", None, "sad"]),
        composite.encode_binary((9, "sad")),
        mood_range.encode_binary(expected_range),
        b"faithful text",
    )

    assert formats == (1, 0, 0, 1, 1, 1, 0)
    assert tuple(decoder(value) for decoder, value in zip(plan, raw, strict=True)) == (
        7,
        "plain",
        "happy",
        ["happy", None, "sad"],
        (9, "sad"),
        expected_range,
        "faithful text",
    )
    with pytest.raises(ProtocolError, match="truncated record"):
        plan[4](b"\x00")


@pytest.mark.issue(695)
def test_malformed_or_conflicting_catalog_rows_fail_loud() -> None:
    malformed = _catalog_row(ENUM_OID, "public.mood", "enum")
    with pytest.raises(ProtocolError, match="malformed type-catalog") as caught:
        parse_type_catalog_rows((malformed,))
    assert caught.value.hint is not None
    assert "Discard the connection" in caught.value.hint

    conflicting = [
        _catalog_row(ENUM_OID, "public.mood", "e"),
        _catalog_row(ENUM_OID, "other.mood", "e"),
    ]
    with pytest.raises(ProtocolError, match="malformed type-catalog"):
        parse_type_catalog_rows(conflicting)


@pytest.mark.issue(695)
def test_dynamic_codec_registries_are_connection_local() -> None:
    first = build_default_registry()
    second = build_default_registry()
    first_metadata = parse_type_catalog_rows((_catalog_row(ENUM_OID, "database_one.mood", "e"),))
    second_metadata = parse_type_catalog_rows((_catalog_row(ENUM_OID, "database_two.status", "e"),))

    register_type_codecs(first, first_metadata)
    register_type_codecs(second, second_metadata)

    assert first.snapshot()[ENUM_OID].name == "database_one.mood"
    assert second.snapshot()[ENUM_OID].name == "database_two.status"
    assert first.snapshot()[ENUM_OID] != second.snapshot()[ENUM_OID]
