"""Immutable, free-threading-shareable configuration for pelt.

:class:`ConnectionConfig` is the resolved connection target; :class:`PoolConfig` wraps it
with pool sizing. Both are ``frozen=True, slots=True, kw_only=True`` — frozen *is* the
free-threading safety guarantee (one immutable object shared across all worker threads,
cf. pounce ``ServerConfig``). Validation and DSN parsing happen in ``__post_init__`` /
``from_dsn`` so an invalid config fails loud at construction, never mid-query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import parse_qs, unquote, urlsplit

# libpq sslmode vocabulary (pelt resolves the matrix in transport, epic E4).
_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})
_PG_SCHEMES = frozenset({"postgres", "postgresql"})


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectionConfig:
    """A single resolved PostgreSQL connection target."""

    host: str = "localhost"
    port: int = 5432
    database: str = ""
    user: str = ""
    password: str = ""
    ssl: str = "prefer"
    connect_timeout: float = 30.0

    SSL_MODES: ClassVar[frozenset[str]] = _SSL_MODES

    def __post_init__(self) -> None:
        if not 0 < self.port <= 65535:
            msg = f"port must be 1-65535 (got {self.port})"
            raise ValueError(msg)
        ssl = self.ssl.lower()
        if ssl not in _SSL_MODES:
            modes = ", ".join(sorted(_SSL_MODES))
            msg = f"ssl must be one of {{{modes}}} (got {self.ssl!r})"
            raise ValueError(msg)
        if self.connect_timeout <= 0:
            msg = f"connect_timeout must be > 0 (got {self.connect_timeout})"
            raise ValueError(msg)
        # Normalize the (validated) sslmode on the frozen instance.
        object.__setattr__(self, "ssl", ssl)

    @classmethod
    def from_dsn(cls, dsn: str) -> ConnectionConfig:
        """Parse a ``postgresql://user:pass@host:port/db?sslmode=...`` DSN.

        Unspecified components fall back to the field defaults. Percent-encoded user and
        password are decoded. Raises :class:`ValueError` on a non-PostgreSQL scheme or a
        malformed port.
        """
        parts = urlsplit(dsn)
        if parts.scheme not in _PG_SCHEMES:
            schemes = " / ".join(sorted(_PG_SCHEMES))
            msg = f"DSN scheme must be {schemes} (got {parts.scheme!r} in {dsn!r})"
            raise ValueError(msg)

        try:
            port = parts.port or 5432
        except ValueError as exc:
            msg = f"invalid port in DSN {dsn!r}: {exc}"
            raise ValueError(msg) from exc

        query = parse_qs(parts.query)
        ssl = query.get("sslmode", ["prefer"])[0]
        connect_timeout = float(query.get("connect_timeout", ["30"])[0])

        return cls(
            host=parts.hostname or "localhost",
            port=port,
            database=parts.path.lstrip("/"),
            user=unquote(parts.username) if parts.username else "",
            password=unquote(parts.password) if parts.password else "",
            ssl=ssl,
            connect_timeout=connect_timeout,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PoolConfig:
    """Pool sizing plus the connection target it manages."""

    connection: ConnectionConfig
    min_size: int = 1
    max_size: int = 10
    statement_cache_size: int = 100

    def __post_init__(self) -> None:
        if self.min_size < 0:
            msg = f"min_size must be >= 0 (got {self.min_size})"
            raise ValueError(msg)
        if self.max_size < 1:
            msg = f"max_size must be >= 1 (got {self.max_size})"
            raise ValueError(msg)
        if self.max_size < self.min_size:
            msg = f"max_size must be >= min_size (got max={self.max_size}, min={self.min_size})"
            raise ValueError(msg)
        if self.statement_cache_size < 0:
            msg = f"statement_cache_size must be >= 0 (got {self.statement_cache_size})"
            raise ValueError(msg)

    @classmethod
    def from_dsn(
        cls,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        statement_cache_size: int = 100,
    ) -> PoolConfig:
        """Build a pool config from a DSN; the Chirp seam's entry point (epic E5)."""
        return cls(
            connection=ConnectionConfig.from_dsn(dsn),
            min_size=min_size,
            max_size=max_size,
            statement_cache_size=statement_cache_size,
        )
