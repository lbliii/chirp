"""Server-catalog metadata for per-connection dynamic PostgreSQL codecs.

This module is sans-I/O.  The connection owns when to execute the generated
catalog query; this module validates its text rows and publishes codecs through
the existing lock-guarded registry.  Only enum, true-array, range, and composite
families are synthesized.  Unknown base, domain, pseudo, and multirange types
remain on PostgreSQL's text result path.

A process-wide :class:`TypeCatalogCache` (keyed by host/port/database) holds an
immutable warm snapshot of discovered :class:`TypeMetadata` so pool checkouts
reuse catalog facts without re-querying ``pg_catalog``.  Codecs remain
connection-local; the cache stores metadata only.  Writers take a short
``threading.Lock`` around publish/invalidate and never hold it across I/O.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
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


@dataclass(frozen=True, slots=True)
class TypeCatalogSnapshot:
    """Immutable warm ``pg_catalog`` facts shared across pool checkouts."""

    by_oid: Mapping[int, TypeMetadata]
    attempted_oids: frozenset[int]


class TypeCatalogCache:
    """Process-wide shared type-catalog cache; immutable after first warm.

    Readers copy the published snapshot reference under a short lock. After
    :meth:`warm`, the snapshot never mutates in place — invalidation clears it
    for a later re-warm (pool reset/close). Never hold the lock across await
    or network I/O.
    """

    __slots__ = ("_identity", "_lock", "_snapshot")

    def __init__(self, identity: tuple[str, int, str]) -> None:
        self._identity = identity
        self._lock = threading.Lock()
        self._snapshot: TypeCatalogSnapshot | None = None

    @property
    def identity(self) -> tuple[str, int, str]:
        """``(host, port, database)`` key that scopes this cache."""
        return self._identity

    @property
    def is_warm(self) -> bool:
        """True once an immutable snapshot has been published."""
        with self._lock:
            return self._snapshot is not None

    def snapshot(self) -> TypeCatalogSnapshot | None:
        """Return the warm snapshot, or ``None`` before the first warm."""
        with self._lock:
            return self._snapshot

    def warm(
        self,
        metadata: Sequence[TypeMetadata],
        attempted_oids: Iterable[int],
    ) -> TypeCatalogSnapshot:
        """Publish an immutable snapshot. First warm wins; later calls no-op."""
        with self._lock:
            existing = self._snapshot
            if existing is not None:
                return existing
            by_oid = {item.oid: item for item in metadata}
            published = TypeCatalogSnapshot(
                by_oid=MappingProxyType(by_oid),
                attempted_oids=frozenset(int(oid) for oid in attempted_oids),
            )
            self._snapshot = published
            return published

    def invalidate(self) -> None:
        """Drop the warm snapshot (pool reset/close)."""
        with self._lock:
            self._snapshot = None


# Process-wide warm catalogs keyed by (host, port, database). Refcounted so
# closing one pool does not invalidate a sibling pool to the same database.
_CATALOG_CACHES: dict[tuple[str, int, str], tuple[TypeCatalogCache, int]] = {}
_CATALOG_CACHES_LOCK = threading.Lock()


def catalog_identity(host: str, port: int, database: str) -> tuple[str, int, str]:
    """Normalize the process-wide cache key for a connection target."""
    return (host, port, database)


def acquire_type_catalog_cache(host: str, port: int, database: str) -> TypeCatalogCache:
    """Return the shared cache for ``identity``, bumping its pool refcount."""
    identity = catalog_identity(host, port, database)
    with _CATALOG_CACHES_LOCK:
        entry = _CATALOG_CACHES.get(identity)
        if entry is None:
            cache = TypeCatalogCache(identity)
            _CATALOG_CACHES[identity] = (cache, 1)
            return cache
        cache, refs = entry
        _CATALOG_CACHES[identity] = (cache, refs + 1)
        return cache


def release_type_catalog_cache(cache: TypeCatalogCache) -> None:
    """Drop one pool reference; invalidate when the last pool releases."""
    identity = cache.identity
    with _CATALOG_CACHES_LOCK:
        entry = _CATALOG_CACHES.get(identity)
        if entry is None:
            return
        current, refs = entry
        if current is not cache:
            return
        if refs > 1:
            _CATALOG_CACHES[identity] = (current, refs - 1)
            return
        del _CATALOG_CACHES[identity]
    cache.invalidate()


def clear_type_catalog_caches() -> None:
    """Drop every process-wide catalog cache (test isolation only)."""
    with _CATALOG_CACHES_LOCK:
        caches = [entry[0] for entry in _CATALOG_CACHES.values()]
        _CATALOG_CACHES.clear()
    for cache in caches:
        cache.invalidate()


def apply_type_catalog_snapshot(
    registry: CodecRegistry,
    attempted_oids: set[int],
    snapshot: TypeCatalogSnapshot | None,
) -> None:
    """Hydrate a connection-local registry from a warm catalog snapshot.

    Marks every attempted OID on the connection ledger and registers codecs for
    cached metadata. Sans-I/O: no ``pg_catalog`` round-trip.
    """
    if snapshot is None:
        return
    attempted_oids.update(snapshot.attempted_oids)
    register_type_codecs(registry, tuple(snapshot.by_oid.values()))


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
    "TypeCatalogCache",
    "TypeCatalogSnapshot",
    "TypeMetadata",
    "acquire_type_catalog_cache",
    "apply_type_catalog_snapshot",
    "build_type_catalog_query",
    "catalog_identity",
    "clear_type_catalog_caches",
    "parse_type_catalog_rows",
    "register_type_codecs",
    "release_type_catalog_cache",
]
