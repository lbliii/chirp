"""pelt error hierarchy.

A single rooted tree (:class:`PeltError`) carrying a stable ``code``, an actionable
``hint``, and a docs anchor — matching the Bengal-stack error-design convention
(cf. pounce ``_errors.py``). While pelt lives in-tree the root also subclasses
:class:`chirp.data.errors.DataError`, so existing ``except DataError`` handlers and the
``Database`` facade keep working unchanged; on extraction to a standalone ``bengal-pelt``
the ``DataError`` base is dropped and ``PeltError`` becomes the sole root.

Every error carries a literal ``PELT_*`` code; a catalog test (epic E7) asserts each code
has a troubleshooting heading. Errors survive pickling across process/thread boundaries via
:meth:`PeltError.__reduce__` so they can cross a worker boundary intact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chirp.data.errors import DataError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "AuthenticationError",
    "PeltConnectionError",
    "PeltError",
    "PeltTimeoutError",
    "PostgresError",
    "ProtocolError",
    "TLSError",
]


class PeltError(DataError):
    """Root of pelt's error tree.

    Carries a stable ``code`` (``PELT_*``), an optional actionable ``hint``, and a docs
    anchor that derives from the code unless overridden.
    """

    default_code = "PELT_E_UNKNOWN"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        hint: str | None = None,
        doc: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.hint = hint
        self.doc = doc or f"docs/troubleshooting.md#{self.code.lower()}"

    def __reduce__(self) -> tuple[Callable[..., PeltError], tuple[object, ...]]:
        # Rebuild via __new__ + state restore so every subclass (with its own __init__
        # signature) round-trips through pickle without bespoke per-class logic.
        return (_reconstruct, (type(self), self.args, self.__dict__.copy()))


def _reconstruct(
    cls: type[PeltError], args: tuple[object, ...], state: dict[str, object]
) -> PeltError:
    err = cls.__new__(cls)
    BaseException.__init__(err, *args)
    err.__dict__.update(state)
    return err


class PeltConnectionError(PeltError):
    """A TCP/Unix connection could not be established, or an open one was lost."""

    default_code = "PELT_CONN_FAILED"


class PeltTimeoutError(PeltError):
    """A pool checkout, connect, or query exceeded its deadline."""

    default_code = "PELT_TIMEOUT"


class ProtocolError(PeltError):
    """The backend sent a message pelt could not parse, or the stream desynced.

    A desync is unrecoverable on that connection: the connection is discarded rather than
    handing back a possibly-corrupt result.
    """

    default_code = "PELT_PROTO_DESYNC"


class AuthenticationError(PeltError):
    """Authentication failed (SCRAM-SHA-256 / MD5 / cleartext) or used an unsupported method."""

    default_code = "PELT_AUTH_FAILED"


class TLSError(PeltError):
    """TLS negotiation failed, or the server refused an SSL connection a mode required."""

    default_code = "PELT_TLS_FAILED"


class PostgresError(PeltError):
    """A server-side ``ErrorResponse``.

    Carries the 5-character SQLSTATE as the stable code (the PG analog of pounce's semantic
    error codes); the server's non-localized severity and optional ``Detail`` ride alongside,
    and the server ``Hint`` field maps onto :attr:`PeltError.hint`.
    """

    default_code = "PELT_PG_ERROR"

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str,
        severity: str,
        detail: str | None = None,
        hint: str | None = None,
        doc: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=f"PELT_PG_{sqlstate}",
            hint=hint,
            doc=doc or "docs/troubleshooting.md#pelt_pg_sqlstate",
        )
        self.sqlstate = sqlstate
        self.severity = severity
        self.detail = detail
