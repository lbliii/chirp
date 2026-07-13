"""Server-catalog metadata for per-connection dynamic PostgreSQL codecs.

This module is sans-I/O.  The connection owns when to execute the generated
catalog query; this module validates its text rows and publishes codecs through
the existing lock-guarded registry.  Only enum, true-array, range, and composite
families are synthesized.  Unknown base, domain, pseudo, and multirange types
remain on PostgreSQL's text result path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from chirp.data.drivers._pelt import _codecs_array
from chirp.data.drivers._pelt import _codecs_composite_range_enum as composite_range
from chirp.data.drivers._pelt._codecs import CodecRegistry
from chirp.data.drivers._pelt.errors import ProtocolError

_MAX_OID = 0xFFFFFFFF


@dataclass(frozen=True, slots=True)
class TypeMetadata:
    """Validated catalog facts needed to construct one parametric codec."""

    oid: int
    name: str
    kind: str
    element_oid: int
    range_subtype_oid: int
    field_oids: tuple[int, ...]

    @property
    def dependencies(self) -> tuple[int, ...]:
        """Return nonzero OIDs whose codecs this type depends on."""
        return tuple(
            dict.fromkeys(
                oid
                for oid in (
                    self.element_oid if self.kind == "a" else 0,
                    self.range_subtype_oid,
                    *self.field_oids,
                )
                if oid
            )
        )


def build_type_catalog_query(oids: Sequence[int]) -> str:
    """Build a schema-qualified read-only lookup for trusted numeric OIDs."""
    normalized = tuple(sorted(set(oids)))
    if not normalized:
        msg = "type discovery requires at least one OID"
        raise ValueError(msg)
    if any(isinstance(oid, bool) or not 0 < oid <= _MAX_OID for oid in normalized):
        msg = "PostgreSQL type OIDs must be integers in the range 1..4294967295"
        raise ValueError(msg)
    oid_list = ", ".join(str(oid) for oid in normalized)
    query = f"""
        SELECT
            t.oid::text AS type_oid,
            (n.nspname || '.' || t.typname)::text AS type_name,
            CASE
                WHEN t.typcategory = 'A' AND t.typelem <> 0 THEN 'a'
                ELSE t.typtype
            END::text AS type_kind,
            t.typelem::text AS element_oid,
            COALESCE(r.rngsubtype, 0)::text AS range_subtype_oid,
            COALESCE(a.attnum, 0)::text AS attribute_number,
            COALESCE(a.atttypid, 0)::text AS attribute_type_oid
        FROM pg_catalog.pg_type AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
        LEFT JOIN pg_catalog.pg_range AS r ON r.rngtypid = t.oid
        LEFT JOIN pg_catalog.pg_attribute AS a
          ON t.typtype = 'c'
         AND a.attrelid = t.typrelid
         AND a.attnum > 0
         AND NOT a.attisdropped
        WHERE t.oid IN ({oid_list})
          AND t.typisdefined
        ORDER BY t.oid, a.attnum
    """  # noqa: S608 - OIDs are range-checked integers, never caller SQL
    return query.strip()


def parse_type_catalog_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[TypeMetadata, ...]:
    """Validate text-format catalog rows and group composite attributes."""
    grouped: dict[int, tuple[str, str, int, int, dict[int, int]]] = {}
    try:
        for row in rows:
            oid = _parse_oid(row["type_oid"])
            name = str(row["type_name"])
            kind = str(row["type_kind"])
            element_oid = _parse_oid(row["element_oid"], allow_zero=True)
            range_subtype_oid = _parse_oid(row["range_subtype_oid"], allow_zero=True)
            attribute_number = int(str(row["attribute_number"]))
            attribute_type_oid = _parse_oid(row["attribute_type_oid"], allow_zero=True)
            if len(kind) != 1 or attribute_number < 0:
                _raise_malformed_catalog()
            existing = grouped.get(oid)
            if existing is None:
                attributes: dict[int, int] = {}
                grouped[oid] = (name, kind, element_oid, range_subtype_oid, attributes)
            else:
                existing_facts = existing[:4]
                if existing_facts != (name, kind, element_oid, range_subtype_oid):
                    _raise_malformed_catalog()
                attributes = existing[4]
            if attribute_number:
                if not attribute_type_oid or attribute_number in attributes:
                    _raise_malformed_catalog()
                attributes[attribute_number] = attribute_type_oid
    except (KeyError, TypeError, ValueError) as exc:
        _raise_malformed_catalog(exc)

    return tuple(
        TypeMetadata(
            oid=oid,
            name=name,
            kind=kind,
            element_oid=element_oid,
            range_subtype_oid=range_subtype_oid,
            field_oids=tuple(attributes[number] for number in sorted(attributes)),
        )
        for oid, (name, kind, element_oid, range_subtype_oid, attributes) in sorted(grouped.items())
    )


def register_type_codecs(
    registry: CodecRegistry,
    metadata: Sequence[TypeMetadata],
) -> tuple[int, ...]:
    """Register every fully resolved enum/array/range/composite codec."""
    registered: list[int] = []
    pending = {item.oid: item for item in metadata if registry.get(item.oid) is None}

    for oid, item in tuple(pending.items()):
        if item.kind != "e":
            continue
        registry.register(composite_range.make_enum_codec(item.oid, item.name))
        registered.append(oid)
        del pending[oid]

    progressed = True
    while pending and progressed:
        progressed = False
        snapshot = registry.snapshot()
        for oid, item in tuple(pending.items()):
            codec = None
            if item.kind == "a" and item.element_oid:
                element = snapshot.get(item.element_oid)
                if element is not None:
                    codec = _codecs_array.make_array_codec(
                        array_oid=item.oid,
                        name=item.name,
                        element_oid=item.element_oid,
                        element_codec=element,
                    )
            elif item.kind == "r" and item.range_subtype_oid:
                subtype = snapshot.get(item.range_subtype_oid)
                if subtype is not None:
                    codec = composite_range.make_range_codec(
                        oid=item.oid,
                        name=item.name,
                        element_decode=subtype.decode_binary,
                        element_encode=subtype.encode_binary,
                    )
            elif item.kind == "c":
                fields = tuple(snapshot.get(field_oid) for field_oid in item.field_oids)
                if all(field is not None for field in fields):
                    codec = composite_range.make_record_codec(
                        oid=item.oid,
                        name=item.name,
                        field_oids=item.field_oids,
                        field_decoders=tuple(
                            field.decode_binary if field is not None else None for field in fields
                        ),
                        field_encoders=tuple(
                            field.encode_binary if field is not None else None for field in fields
                        ),
                    )
            if codec is None:
                continue
            registry.register(codec)
            registered.append(oid)
            del pending[oid]
            progressed = True

    return tuple(sorted(registered))


def _parse_oid(value: Any, *, allow_zero: bool = False) -> int:
    oid = int(str(value))
    lower = 0 if allow_zero else 1
    if not lower <= oid <= _MAX_OID:
        raise ValueError
    return oid


def _raise_malformed_catalog(cause: BaseException | None = None) -> NoReturn:
    msg = "PostgreSQL returned malformed type-catalog metadata"
    error = ProtocolError(
        msg,
        hint="Discard the connection and verify pg_catalog visibility and server compatibility.",
    )
    if cause is None:
        raise error
    raise error from cause


__all__ = [
    "TypeMetadata",
    "build_type_catalog_query",
    "parse_type_catalog_rows",
    "register_type_codecs",
]
