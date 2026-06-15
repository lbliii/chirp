"""Typed, immutable representations of PostgreSQL backend (server → client) messages.

Every message is ``frozen=True, slots=True`` — they are produced by the sans-I/O framer
(:mod:`._framing`) and handed cheaply between free-threaded workers; frozenness is the
thread-safety guarantee. The :data:`PGMessage` union (PEP 695) is the single typed value the
framer returns. This module touches no socket and no anyio.

Only the message set pelt needs for the E1 spine + the extended-query protocol (epic E3) is
modelled here; COPY and replication messages are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- field-type bytes carried inside Error/NoticeResponse -------------------
# (subset of the PostgreSQL error/notice field codes we surface)
_ERR_SEVERITY = "S"
_ERR_SEVERITY_NONLOCALIZED = "V"
_ERR_CODE = "C"
_ERR_MESSAGE = "M"
_ERR_DETAIL = "D"
_ERR_HINT = "H"


# --- authentication (tag 'R') -----------------------------------------------
@dataclass(frozen=True, slots=True)
class AuthenticationOk:
    """``AuthenticationOk`` — the server accepted the credentials."""


@dataclass(frozen=True, slots=True)
class AuthenticationCleartextPassword:
    """The server wants a cleartext password."""


@dataclass(frozen=True, slots=True)
class AuthenticationMD5Password:
    """The server wants an MD5-hashed password, salted with ``salt``."""

    salt: bytes


@dataclass(frozen=True, slots=True)
class AuthenticationSASL:
    """The server offers SASL authentication with these mechanisms (e.g. SCRAM-SHA-256)."""

    mechanisms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthenticationSASLContinue:
    """A SASL challenge from the server."""

    data: bytes


@dataclass(frozen=True, slots=True)
class AuthenticationSASLFinal:
    """The final SASL message from the server."""

    data: bytes


# --- session setup ----------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ParameterStatus:
    """A server runtime parameter report (tag ``'S'``), e.g. ``server_version``."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class BackendKeyData:
    """Cancellation key material (tag ``'K'``) — needed to cancel a running query."""

    pid: int
    secret_key: int


@dataclass(frozen=True, slots=True)
class ReadyForQuery:
    """The server is ready (tag ``'Z'``). ``status`` is ``'I'`` idle, ``'T'`` in-transaction,
    or ``'E'`` failed-transaction."""

    status: str


# --- query results ----------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FieldDescription:
    """One column descriptor within a :class:`RowDescription`."""

    name: str
    table_oid: int
    column_attr: int
    type_oid: int
    type_size: int
    type_modifier: int
    format_code: int


@dataclass(frozen=True, slots=True)
class RowDescription:
    """The column layout of a result set (tag ``'T'``)."""

    fields: tuple[FieldDescription, ...]


@dataclass(frozen=True, slots=True)
class DataRow:
    """One result row (tag ``'D'``). Each value is the raw wire bytes or ``None`` for SQL NULL;
    decoding to Python objects happens later via the codec plan (epic E2)."""

    values: tuple[bytes | None, ...]


@dataclass(frozen=True, slots=True)
class CommandComplete:
    """A command finished (tag ``'C'``). ``tag`` is e.g. ``'INSERT 0 1'`` / ``'SELECT 5'``."""

    tag: str


@dataclass(frozen=True, slots=True)
class ParameterDescription:
    """Parameter OIDs for a prepared statement (tag ``'t'``)."""

    type_oids: tuple[int, ...]


# --- notices / errors / async notifications ---------------------------------
@dataclass(frozen=True, slots=True)
class ErrorResponse:
    """A server error (tag ``'E'``). Fields are kept as ``(code, value)`` pairs to stay
    hashable + frozen; the common ones are exposed as properties."""

    fields: tuple[tuple[str, str], ...]

    def _get(self, code: str) -> str | None:
        for field_code, value in self.fields:
            if field_code == code:
                return value
        return None

    @property
    def severity(self) -> str:
        return self._get(_ERR_SEVERITY_NONLOCALIZED) or self._get(_ERR_SEVERITY) or "ERROR"

    @property
    def sqlstate(self) -> str:
        return self._get(_ERR_CODE) or "XX000"

    @property
    def message_text(self) -> str:
        return self._get(_ERR_MESSAGE) or ""

    @property
    def detail(self) -> str | None:
        return self._get(_ERR_DETAIL)

    @property
    def hint(self) -> str | None:
        return self._get(_ERR_HINT)


@dataclass(frozen=True, slots=True)
class NoticeResponse:
    """A non-fatal notice (tag ``'N'``). Same structure as :class:`ErrorResponse`."""

    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class NotificationResponse:
    """An async ``NOTIFY`` payload (tag ``'A'``) — drives LISTEN/NOTIFY (epic E5)."""

    pid: int
    channel: str
    payload: str


# --- contentless markers (extended-query protocol) --------------------------
@dataclass(frozen=True, slots=True)
class ParseComplete:
    """Tag ``'1'``."""


@dataclass(frozen=True, slots=True)
class BindComplete:
    """Tag ``'2'``."""


@dataclass(frozen=True, slots=True)
class CloseComplete:
    """Tag ``'3'``."""


@dataclass(frozen=True, slots=True)
class NoData:
    """Tag ``'n'`` — a prepared statement returns no rows."""


@dataclass(frozen=True, slots=True)
class PortalSuspended:
    """Tag ``'s'`` — an ``Execute`` row limit was reached; more rows remain."""


@dataclass(frozen=True, slots=True)
class EmptyQueryResponse:
    """Tag ``'I'`` — the query string was empty."""


type PGMessage = (
    AuthenticationOk
    | AuthenticationCleartextPassword
    | AuthenticationMD5Password
    | AuthenticationSASL
    | AuthenticationSASLContinue
    | AuthenticationSASLFinal
    | ParameterStatus
    | BackendKeyData
    | ReadyForQuery
    | RowDescription
    | DataRow
    | CommandComplete
    | ParameterDescription
    | ErrorResponse
    | NoticeResponse
    | NotificationResponse
    | ParseComplete
    | BindComplete
    | CloseComplete
    | NoData
    | PortalSuspended
    | EmptyQueryResponse
)
