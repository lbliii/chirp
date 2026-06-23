"""Sans-I/O connection protocol engine: backend bytes in → high-level events + outbound bytes.

:class:`SimpleQueryProtocol` is the pure state machine that drives one PostgreSQL connection.
It owns the inbound byte buffer, drains complete messages with :func:`._framing.parse_message`
(carrying partial reads forward), and folds the wire-level :data:`PGMessage` stream into a
small set of high-level :data:`ProtocolEvent` objects. Outbound work goes the other way: the
``send_*`` helpers return frontend bytes (via :mod:`._builder`) and advance the state, but the
engine never touches a socket — connection / pool own anyio I/O in a later epic. This keeps
the protocol fuzzable in isolation and parallelizable across free-threaded workers.

Two engines live here. :class:`SimpleQueryProtocol` (E3 core) models the **simple-query**
protocol: STARTUP/auth → READY, then one ``Query`` in flight (RowDescription → DataRow* →
CommandComplete → ReadyForQuery) and back to READY. :class:`ExtendedQueryProtocol` models the
**extended-query** path — Parse/Bind/Describe/Execute/Sync with ``$N`` parameters — plus a
single-owner :class:`PreparedStatementCache` (LRU, bounded, clean-miss on plan invalidation)
and server-side cursors (an ``Execute`` row limit yields ``PortalSuspended``; :meth:`resume`
fetches the next batch). Cancellation lands in a later epic. Raw column bytes are passed
through untouched — decoding against the codec plan is the next layer's job; both engines only
pair each :class:`DataRowEvent` with its :class:`RowDescription`.

Desync discipline: any message that is illegal for the current state raises
:class:`ProtocolError`. :func:`parse_message` already raises ``ProtocolError`` on malformed
bytes, so a corrupt object is never handed back; a desynced connection is unrecoverable and
must be discarded by the I/O layer.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, NoReturn

from chirp.data.drivers._pelt import _builder
from chirp.data.drivers._pelt._framing import parse_message
from chirp.data.drivers._pelt._messages import (
    AuthenticationCleartextPassword,
    AuthenticationMD5Password,
    AuthenticationOk,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
    BackendKeyData,
    BindComplete,
    CloseComplete,
    CommandComplete,
    DataRow,
    EmptyQueryResponse,
    ErrorResponse,
    NoData,
    NoticeResponse,
    NotificationResponse,
    ParameterDescription,
    ParameterStatus,
    ParseComplete,
    PortalSuspended,
    ReadyForQuery,
    RowDescription,
)
from chirp.data.drivers._pelt.errors import PostgresError, ProtocolError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chirp.data.drivers._pelt._messages import PGMessage


# --- connection lifecycle states --------------------------------------------
class ProtocolState(Enum):
    """The connection's wire-protocol phase.

    The simple-query lifecycle is ``STARTUP → AUTHENTICATING → READY ⇄ BUSY``. ``READY``
    tracks the most recent ``ReadyForQuery`` transaction status; ``BUSY`` means a ``Query`` is
    in flight and the engine is folding its result stream. ``CLOSED`` is reached after the
    backend stops talking (graceful ``Terminate`` is initiated by the I/O layer).
    """

    STARTUP = "startup"
    AUTHENTICATING = "authenticating"
    READY = "ready"
    BUSY = "busy"
    CLOSED = "closed"


# --- transaction status (mirrors the ReadyForQuery 'status' byte) -----------
class TransactionStatus(Enum):
    """The backend's transaction state, reported by every ``ReadyForQuery``."""

    IDLE = "I"
    IN_TRANSACTION = "T"
    IN_FAILED_TRANSACTION = "E"


def _transaction_status(status: str) -> TransactionStatus:
    try:
        return TransactionStatus(status)
    except ValueError as exc:
        msg = f"unknown ReadyForQuery transaction status {status!r}"
        raise ProtocolError(msg) from exc


# An auth challenge (anything but AuthenticationOk) the I/O layer must answer. The tuple form
# is for isinstance dispatch; the type alias keeps the event field and handler signature exact.
_AUTH_REQUEST_TYPES = (
    AuthenticationCleartextPassword,
    AuthenticationMD5Password,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
)
type AuthRequest = (
    AuthenticationCleartextPassword
    | AuthenticationMD5Password
    | AuthenticationSASL
    | AuthenticationSASLContinue
    | AuthenticationSASLFinal
)


# --- high-level events the engine surfaces ----------------------------------
@dataclass(frozen=True, slots=True)
class AuthOkEvent:
    """``AuthenticationOk`` was received — credentials accepted, session setup begins."""


@dataclass(frozen=True, slots=True)
class AuthRequestEvent:
    """The backend requested authentication material the I/O layer must answer.

    ``request`` is the originating auth message (cleartext / MD5 / SASL*); the auth layer
    (epic E4) inspects it and replies with a ``PasswordMessage``."""

    request: AuthRequest


@dataclass(frozen=True, slots=True)
class ReadyEvent:
    """``ReadyForQuery`` — the backend is idle and accepting a new command."""

    transaction_status: TransactionStatus


@dataclass(frozen=True, slots=True)
class RowDescriptionEvent:
    """The column layout for the rows that follow within the current query."""

    description: RowDescription


@dataclass(frozen=True, slots=True)
class DataRowEvent:
    """One result row, paired with the :class:`RowDescription` it belongs to.

    ``row.values`` are still raw wire bytes (or ``None`` for SQL NULL); decoding against the
    codec plan happens in the next layer. ``description`` is never ``None`` — a ``DataRow``
    with no preceding ``RowDescription`` is a desync and raises :class:`ProtocolError`."""

    row: DataRow
    description: RowDescription


@dataclass(frozen=True, slots=True)
class CommandCompleteEvent:
    """A command in the current query finished. ``tag`` is e.g. ``'SELECT 2'`` / ``'INSERT 0 1'``."""

    tag: str


@dataclass(frozen=True, slots=True)
class EmptyQueryEvent:
    """The submitted query string was empty (``EmptyQueryResponse``)."""


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """A server ``ErrorResponse`` mapped onto a :class:`PostgresError`.

    The engine surfaces the error rather than raising it so the I/O layer decides whether to
    raise (the common case) or log; either way the trailing ``ReadyForQuery`` resynchronizes
    the connection."""

    error: PostgresError


@dataclass(frozen=True, slots=True)
class ParameterStatusEvent:
    """A server runtime parameter report (e.g. ``server_version``), deliverable any time."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class BackendKeyDataEvent:
    """Cancellation key material (PID + secret), captured during session setup."""

    pid: int
    secret_key: int


@dataclass(frozen=True, slots=True)
class NoticeEvent:
    """A non-fatal server notice, deliverable any time. ``fields`` are ``(code, value)`` pairs."""

    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class NotificationEvent:
    """An async ``NOTIFY`` payload (LISTEN/NOTIFY), deliverable any time."""

    pid: int
    channel: str
    payload: str


# --- extended-query events (epic E3) ----------------------------------------
@dataclass(frozen=True, slots=True)
class ParseCompleteEvent:
    """``ParseComplete`` — the ``Parse`` was accepted and the named statement now exists."""


@dataclass(frozen=True, slots=True)
class BindCompleteEvent:
    """``BindComplete`` — parameters were bound and the named portal now exists."""


@dataclass(frozen=True, slots=True)
class CloseCompleteEvent:
    """``CloseComplete`` — the backend dropped the named statement or portal a ``Close`` targeted.

    The acknowledgement of a ``Close`` request (the orphaned ``pelt_stmt_N`` statements that
    :meth:`ExtendedQueryProtocol.drain_pending_close` surfaces are closed this way). It carries
    no payload and never desyncs: a ``CloseComplete`` is always a legal ``Close`` ack, so the
    engine surfaces it rather than treating it as an illegal message."""


@dataclass(frozen=True, slots=True)
class ParameterDescriptionEvent:
    """``ParameterDescription`` — the OIDs the server inferred / accepted for ``$N`` params.

    Surfaced after a ``Describe`` of a statement; the cache stores these so a later prepare of
    the same SQL with the same explicit param OIDs is a clean hit (and a different set is a
    clean miss → re-prepare)."""

    type_oids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class NoDataEvent:
    """``NoData`` — the described statement/portal returns no rows (e.g. an ``INSERT``)."""


@dataclass(frozen=True, slots=True)
class PortalSuspendedEvent:
    """``PortalSuspended`` — an ``Execute`` row limit was reached and more rows remain.

    The portal is left open; the I/O layer resumes by issuing another ``Execute`` on the same
    portal (see :meth:`ExtendedQueryProtocol.resume_execute`). This is the server-side cursor /
    prefetch-batching primitive that powers ``Database.stream()``."""


type ProtocolEvent = (
    AuthOkEvent
    | AuthRequestEvent
    | ReadyEvent
    | RowDescriptionEvent
    | DataRowEvent
    | CommandCompleteEvent
    | EmptyQueryEvent
    | ErrorEvent
    | ParameterStatusEvent
    | BackendKeyDataEvent
    | NoticeEvent
    | NotificationEvent
    | ParseCompleteEvent
    | BindCompleteEvent
    | CloseCompleteEvent
    | ParameterDescriptionEvent
    | NoDataEvent
    | PortalSuspendedEvent
)


def map_error_response(error: ErrorResponse) -> PostgresError:
    """Map a backend ``ErrorResponse`` onto a :class:`PostgresError`, pulling the standard
    fields off the message's properties. The SQLSTATE becomes the error's stable ``PELT_PG_*``
    code; the server ``Hint`` rides onto :attr:`PeltError.hint`."""
    return PostgresError(
        error.message_text,
        sqlstate=error.sqlstate,
        severity=error.severity,
        detail=error.detail,
        hint=error.hint,
    )


# --- the engine -------------------------------------------------------------
@dataclass(slots=True)
class SimpleQueryProtocol:
    """A single PostgreSQL connection's sans-I/O protocol state machine.

    Per-connection state is single-owner (one engine per connection, never shared between
    threads), so it is mutable and lock-free by construction — the free-threading discipline
    for owned state. Feed inbound bytes with :meth:`receive_bytes` (any chunking, including one
    byte at a time, is fine — partial reads are buffered); drive outbound work with the
    ``send_*`` helpers, which return frontend bytes and advance the state.
    """

    state: ProtocolState = ProtocolState.STARTUP
    transaction_status: TransactionStatus | None = None
    backend_pid: int | None = None
    backend_secret_key: int | None = None
    _buffer: bytearray = field(default_factory=bytearray, repr=False)
    _row_description: RowDescription | None = field(default=None, repr=False)

    # -- outbound (frontend) -------------------------------------------------
    def send_startup(self, *, user: str, database: str = "", **params: str) -> bytes:
        """Build the untagged StartupMessage and enter the AUTHENTICATING phase.

        Legal only from ``STARTUP``; calling it twice is a programmer misuse (raises
        :class:`ValueError`, mirroring ``_builder.frame``)."""
        if self.state is not ProtocolState.STARTUP:
            msg = f"send_startup is only valid in STARTUP (state is {self.state.name})"
            raise ValueError(msg)
        self.state = ProtocolState.AUTHENTICATING
        return _builder.build_startup(user=user, database=database, **params)

    def send_query(self, sql: str) -> bytes:
        """Build a simple-protocol ``Query`` and enter the BUSY phase.

        Legal only from ``READY`` (the backend must have sent a ``ReadyForQuery``). Issuing a
        query while one is already in flight is a programmer misuse (raises
        :class:`ValueError`)."""
        if self.state is not ProtocolState.READY:
            msg = f"send_query is only valid in READY (state is {self.state.name})"
            raise ValueError(msg)
        self.state = ProtocolState.BUSY
        self._row_description = None
        return _builder.build_query(sql)

    def send_terminate(self) -> bytes:
        """Build a ``Terminate`` and mark the engine CLOSED."""
        self.state = ProtocolState.CLOSED
        return _builder.build_terminate()

    # -- inbound (backend) ---------------------------------------------------
    def receive_bytes(self, data: bytes) -> list[ProtocolEvent]:
        """Append ``data`` to the inbound buffer, drain every complete message, and return the
        high-level events they fold into.

        Partial reads are carried forward in the buffer, so any chunking — including a single
        byte at a time — reconstructs the same event sequence as one large read. Raises
        :class:`ProtocolError` on a malformed frame (via :func:`parse_message`) or on a message
        that is illegal for the current state.
        """
        if data:
            self._buffer += data
        events: list[ProtocolEvent] = []
        while True:
            # parse_message takes bytes | memoryview; a 0-copy view over the bytearray avoids a
            # per-iteration copy of the (possibly large) carry-forward buffer.
            message, consumed = parse_message(memoryview(self._buffer))
            if message is None:
                break
            del self._buffer[:consumed]
            event = self._dispatch(message)
            if event is not None:
                events.append(event)
        return events

    def _dispatch(self, message: PGMessage) -> ProtocolEvent | None:
        # Side-band messages may arrive in any non-closed state and never desync the stream.
        if isinstance(message, ParameterStatus):
            self._require_open(message)
            return ParameterStatusEvent(name=message.name, value=message.value)
        if isinstance(message, NoticeResponse):
            self._require_open(message)
            return NoticeEvent(fields=message.fields)
        if isinstance(message, NotificationResponse):
            self._require_open(message)
            return NotificationEvent(
                pid=message.pid, channel=message.channel, payload=message.payload
            )
        if isinstance(message, BackendKeyData):
            return self._on_backend_key_data(message)

        # ReadyForQuery and ErrorResponse can close out either the setup or the query phase.
        if isinstance(message, ReadyForQuery):
            return self._on_ready(message)
        if isinstance(message, ErrorResponse):
            return self._on_error(message)

        # Authentication is only legal while STARTUP/AUTHENTICATING.
        if isinstance(message, AuthenticationOk):
            return self._on_auth_ok(message)
        if isinstance(message, _AUTH_REQUEST_TYPES):
            return self._on_auth_request(message)

        # Query-result messages are only legal while BUSY.
        if isinstance(message, RowDescription):
            return self._on_row_description(message)
        if isinstance(message, DataRow):
            return self._on_data_row(message)
        if isinstance(message, CommandComplete):
            return self._on_command_complete(message)
        if isinstance(message, EmptyQueryResponse):
            return self._on_empty_query(message)

        self._desync(message)

    # -- per-message handlers ------------------------------------------------
    def _on_backend_key_data(self, message: BackendKeyData) -> ProtocolEvent:
        # Captured during session setup so the cancel path (later epic) has the PID + secret;
        # also surfaced as an event. Illegal once CLOSED.
        if self.state is ProtocolState.CLOSED:
            self._desync(message)
        self.backend_pid = message.pid
        self.backend_secret_key = message.secret_key
        return BackendKeyDataEvent(pid=message.pid, secret_key=message.secret_key)

    def _on_ready(self, message: ReadyForQuery) -> ProtocolEvent:
        # ReadyForQuery legally terminates the setup phase OR a query; nothing else.
        if self.state not in (ProtocolState.AUTHENTICATING, ProtocolState.BUSY):
            self._desync(message)
        status = _transaction_status(message.status)
        self.state = ProtocolState.READY
        self.transaction_status = status
        self._row_description = None
        return ReadyEvent(transaction_status=status)

    def _on_error(self, message: ErrorResponse) -> ProtocolEvent:
        # An ErrorResponse is legal whenever the backend is mid-exchange; the trailing
        # ReadyForQuery resynchronizes. It is illegal once CLOSED.
        if self.state is ProtocolState.CLOSED:
            self._desync(message)
        return ErrorEvent(error=map_error_response(message))

    def _on_auth_ok(self, message: AuthenticationOk) -> ProtocolEvent:
        if self.state not in (ProtocolState.STARTUP, ProtocolState.AUTHENTICATING):
            self._desync(message)
        self.state = ProtocolState.AUTHENTICATING
        return AuthOkEvent()

    def _on_auth_request(self, message: AuthRequest) -> ProtocolEvent:
        if self.state not in (ProtocolState.STARTUP, ProtocolState.AUTHENTICATING):
            self._desync(message)
        self.state = ProtocolState.AUTHENTICATING
        return AuthRequestEvent(request=message)

    def _on_row_description(self, message: RowDescription) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        self._row_description = message
        return RowDescriptionEvent(description=message)

    def _on_data_row(self, message: DataRow) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        if self._row_description is None:
            msg = "DataRow received with no preceding RowDescription"
            raise ProtocolError(msg)
        return DataRowEvent(row=message, description=self._row_description)

    def _on_command_complete(self, message: CommandComplete) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        # A simple Query can carry several statements; reset the layout between them, but stay
        # BUSY until the trailing ReadyForQuery.
        self._row_description = None
        return CommandCompleteEvent(tag=message.tag)

    def _on_empty_query(self, message: EmptyQueryResponse) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        self._row_description = None
        return EmptyQueryEvent()

    # -- desync helpers ------------------------------------------------------
    def _require_open(self, message: PGMessage) -> None:
        if self.state is ProtocolState.CLOSED:
            self._desync(message)

    def _desync(self, message: PGMessage) -> NoReturn:
        msg = (
            f"unexpected {type(message).__name__} in state {self.state.name}: "
            f"connection desynced and must be discarded"
        )
        raise ProtocolError(msg)


# --- prepared-statement cache -----------------------------------------------
@dataclass(frozen=True, slots=True)
class PreparedStatement:
    """A cache entry: a server-side prepared statement and the plan it was prepared against.

    ``param_oids`` is the explicit OID list sent in the ``Parse`` (empty when the server was
    asked to infer). ``resolved_param_oids`` is what the backend reported back in its
    ``ParameterDescription`` (``None`` until a ``Describe`` resolves it). A later prepare whose
    resolved OIDs disagree is a *type mismatch* — the entry is evicted and re-prepared rather
    than reusing a stale plan."""

    name: str
    sql: str
    param_oids: tuple[int, ...]
    version: int
    resolved_param_oids: tuple[int, ...] | None = None
    row_description: RowDescription | None = None


class PreparedStatementCache:
    """A bounded, per-connection LRU cache of prepared statements.

    **Single-owner, lock-free by design.** One cache belongs to one
    :class:`ExtendedQueryProtocol`, which belongs to one connection, which is never shared
    between threads (the free-threading discipline for owned state — cf. ``SimpleQueryProtocol``).
    The codec *registry* is the shared-mutable structure that needs a lock; this cache is not.
    Putting a lock here would be cargo-culted overhead on a hot path that is provably single-owner.

    Keyed by ``(sql, tuple(param_oids))`` so the same SQL prepared with different explicit
    parameter types gets distinct plans. Bounded by ``size``; reaching capacity evicts the
    least-recently-used entry (LRU via insertion-ordered :class:`~collections.OrderedDict`,
    moved-to-end on every hit). ``size == 0`` disables caching entirely — every lookup misses
    and nothing is stored.

    Plan invalidation is a clean *miss*, never a stale reuse: a :meth:`get` against a stored
    entry whose ``version`` is older than the cache's current generation, or whose resolved
    parameter OIDs disagree with the caller's expectation, drops the entry and returns ``None``
    so the caller re-prepares. :meth:`bump_version` advances the generation (e.g. after a DDL /
    schema change the I/O layer observes), invalidating every older entry lazily on next touch.
    """

    __slots__ = ("_entries", "_seq", "_version", "size")

    def __init__(self, size: int = 100) -> None:
        if size < 0:
            msg = f"statement_cache_size must be >= 0 (got {size})"
            raise ValueError(msg)
        self.size = size
        self._version = 0
        self._seq = 0
        # Insertion-ordered: the front is least-recently-used, the back most-recent.
        self._entries: OrderedDict[tuple[str, tuple[int, ...]], PreparedStatement] = OrderedDict()

    @staticmethod
    def _key(sql: str, param_oids: Sequence[int]) -> tuple[str, tuple[int, ...]]:
        return (sql, tuple(param_oids))

    @property
    def version(self) -> int:
        """The current plan generation; entries prepared before it are invalid."""
        return self._version

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: object) -> bool:
        # Membership does not promote LRU order and does not evict on version skew; use get()
        # for the load-bearing lookup. This is here for tests / introspection only.
        return key in self._entries

    def bump_version(self) -> int:
        """Advance the plan generation, invalidating every cached entry on its next touch.

        Returns the new version. Use after a schema change (a new column type, a dropped/renamed
        relation) so the next prepare of any cached SQL re-plans against the new catalog rather
        than reusing a plan the backend would reject or mis-decode."""
        self._version += 1
        return self._version

    def next_statement_name(self) -> str:
        """A stable, collision-free server-side statement name (``pelt_stmt_<n>``).

        Monotonic per cache, so names never alias across evict/re-prepare cycles within one
        connection — reusing a name for a different plan is a desync footgun."""
        self._seq += 1
        return f"pelt_stmt_{self._seq}"

    def get(self, sql: str, param_oids: Sequence[int] = ()) -> PreparedStatement | None:
        """Look up a live plan for ``(sql, param_oids)``; a clean miss returns ``None``.

        A hit moves the entry to the most-recently-used end. A stored entry from an older plan
        generation is evicted (clean miss → caller re-prepares). Caching is disabled when
        ``size == 0``."""
        if self.size == 0:
            return None
        key = self._key(sql, param_oids)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.version != self._version:
            # Stale plan (a schema/version change happened): evict and miss rather than reuse.
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry

    def put(
        self,
        sql: str,
        param_oids: Sequence[int],
        *,
        name: str,
        resolved_param_oids: tuple[int, ...] | None = None,
        row_description: RowDescription | None = None,
    ) -> PreparedStatement | None:
        """Store a freshly prepared statement; evict the LRU entry if at capacity.

        Stamped with the current plan generation. Returns the new entry, or ``None`` when
        caching is disabled (``size == 0``) — the caller still uses the statement for this one
        execution, it just is not retained."""
        if self.size == 0:
            return None
        key = self._key(sql, param_oids)
        existing = self._entries.get(key)
        if row_description is None and existing is not None:
            row_description = existing.row_description
        entry = PreparedStatement(
            name=name,
            sql=sql,
            param_oids=tuple(param_oids),
            version=self._version,
            resolved_param_oids=resolved_param_oids,
            row_description=row_description,
        )
        # Refreshing an existing key must not double-count toward the bound.
        if key in self._entries:
            del self._entries[key]
        self._entries[key] = entry
        evicted: PreparedStatement | None = None
        if len(self._entries) > self.size:
            _, evicted = self._entries.popitem(last=False)  # least-recently-used
        return evicted

    def invalidate(self, sql: str, param_oids: Sequence[int] = ()) -> None:
        """Drop one entry (e.g. after a type-mismatch is detected on resolve). Idempotent."""
        self._entries.pop(self._key(sql, param_oids), None)

    def clear(self) -> None:
        """Drop every cached plan (e.g. on connection reset)."""
        self._entries.clear()


# --- extended-query engine --------------------------------------------------
@dataclass(slots=True)
class ExtendedQueryProtocol:
    """The extended-query (Parse/Bind/Describe/Execute/Sync) state machine for one connection.

    Single-owner and lock-free for the same reason as :class:`SimpleQueryProtocol`: one engine
    per connection, never shared. It shares the :class:`ProtocolState` / :class:`TransactionStatus`
    vocabulary and the side-band / error / ReadyForQuery handling, then layers the extended
    message set on top:

    - **Prepare** (:meth:`send_parse_describe`): ``Parse`` → ``Describe(statement)`` → ``Sync``.
      The backend answers ``ParseComplete`` → ``ParameterDescription`` → ``RowDescription`` |
      ``NoData`` → ``ReadyForQuery``. The resolved parameter OIDs are folded back into the
      cache entry so a future prepare can detect a type mismatch.
    - **Execute** (:meth:`send_bind_execute`): ``Bind`` → ``Execute(max_rows)`` → ``Sync``.
      The backend answers ``BindComplete`` → ``DataRow*`` → (``CommandComplete`` |
      ``PortalSuspended``) → ``ReadyForQuery``.
    - **Resume** (:meth:`resume_execute`): another ``Execute`` → ``Sync`` against an open
      portal that previously :class:`PortalSuspendedEvent`-suspended — the server-side cursor.

    The whole Parse/Bind/Execute pipeline is sent as one batch terminated by a single ``Sync``,
    so the backend reports any error once and a single trailing ``ReadyForQuery`` resynchronizes.
    Raw column bytes pass through untouched; decoding against the codec plan is the next layer.

    Owns an optional :class:`PreparedStatementCache`. The high-level prepare/execute helpers
    consult and update it, but the cache can also be driven directly for tests.
    """

    state: ProtocolState = ProtocolState.READY
    transaction_status: TransactionStatus | None = None
    cache: PreparedStatementCache = field(default_factory=PreparedStatementCache)
    _buffer: bytearray = field(default_factory=bytearray, repr=False)
    _row_description: RowDescription | None = field(default=None, repr=False)
    # The portal the most-recent Execute targeted; resume_execute() re-Executes it.
    _open_portal: str | None = field(default=None, repr=False)
    # The cache key of a prepare batch the backend has not yet accepted. The entry is stored
    # eagerly (so concurrent prepares of the same SQL share a name), but its server-side
    # statement does not exist until ParseComplete. If the backend rejects the Parse with an
    # ErrorResponse, _on_error invalidates this key so the failed plan is never reused against a
    # statement that was never created (which would desync into SQLSTATE 26000). Cleared on the
    # terminal ReadyForQuery once the prepare has succeeded.
    _pending_prepare: tuple[str, tuple[int, ...]] | None = field(default=None, repr=False)
    # Server-side statements the backend created (pelt_stmt_N) that the cache evicted (LRU /
    # version bump). They are orphaned until the I/O layer issues a Close; drain_pending_close()
    # surfaces them so connection/pool can close them (Close lands in E4+). Until then this is a
    # bounded, explicit leak ledger, never a silent drop.
    _pending_close: list[PreparedStatement] = field(default_factory=list, repr=False)

    # -- outbound (frontend) -------------------------------------------------
    def prepare(
        self, sql: str, param_oids: Sequence[int] = ()
    ) -> tuple[PreparedStatement, bytes | None]:
        """Resolve ``(sql, param_oids)`` to a prepared statement, preparing it on a cache miss.

        Returns ``(statement, outbound)``. On a **hit**, ``outbound`` is ``None`` (no wire
        traffic — reuse the server-side plan). On a **miss**, ``outbound`` is the
        ``Parse``/``Describe``/``Sync`` batch to send and the engine enters ``BUSY``; the caller
        feeds the reply to :meth:`receive_bytes` and then calls :meth:`record_parameter_description`
        (the engine does this automatically) before the statement is fully usable.

        Legal only from ``READY``. A miss generates a stable statement name and stores the entry
        eagerly (so concurrent prepares of the same SQL share it); :meth:`receive_bytes` later
        folds the resolved parameter OIDs into the stored entry. The eagerly-stored entry is only
        provisional until the backend's ``ParseComplete``: an ``ErrorResponse`` for this Parse
        invalidates it (see :attr:`_pending_prepare`) so the next prepare is a clean miss rather
        than a hit on a statement the server never created. If storing the entry evicts an LRU
        victim, that orphaned server-side statement is queued for :meth:`drain_pending_close`."""
        if self.state is not ProtocolState.READY:
            msg = f"prepare is only valid in READY (state is {self.state.name})"
            raise ValueError(msg)
        hit = self.cache.get(sql, param_oids)
        if hit is not None:
            return hit, None
        name = self.cache.next_statement_name()
        # cache.put returns the LRU victim it evicted, if any. That victim is a statement the
        # backend already created; queue it for Close rather than dropping it (a server-side
        # prepared-statement leak). Until Close is wired (E4+) this is an explicit ledger.
        evicted = self.cache.put(sql, param_oids, name=name)
        if evicted is not None:
            self._pending_close.append(evicted)
        statement = self.cache.get(sql, param_oids) or PreparedStatement(
            name=name, sql=sql, param_oids=tuple(param_oids), version=self.cache.version
        )
        # Mark this prepare in flight so a Parse rejection (ErrorResponse before ParseComplete)
        # invalidates the just-stored, never-created entry.
        self._pending_prepare = (sql, tuple(param_oids))
        outbound = self.send_parse_describe(name=name, sql=sql, param_oids=param_oids)
        return statement, outbound

    def send_parse_describe(self, *, name: str, sql: str, param_oids: Sequence[int] = ()) -> bytes:
        """Build the ``Parse`` → ``Describe(statement)`` → ``Sync`` batch and enter ``BUSY``.

        Lower-level than :meth:`prepare` (no cache consultation). Legal only from ``READY``."""
        if self.state is not ProtocolState.READY:
            msg = f"send_parse_describe is only valid in READY (state is {self.state.name})"
            raise ValueError(msg)
        self.state = ProtocolState.BUSY
        self._row_description = None
        self._open_portal = None
        return (
            _builder.build_parse(name=name, query=sql, param_oids=param_oids)
            + _builder.build_describe(kind="S", name=name)
            + _builder.build_sync()
        )

    def send_bind_execute(
        self,
        *,
        statement: str,
        params: Sequence[bytes | None] = (),
        portal: str = "",
        max_rows: int = 0,
    ) -> bytes:
        """Build the ``Bind`` → ``Execute(max_rows)`` → ``Sync`` batch and enter ``BUSY``.

        ``max_rows == 0`` fetches all rows; a positive ``max_rows`` is the server-side cursor /
        prefetch batch size — the backend returns at most that many ``DataRow`` then a
        :class:`PortalSuspendedEvent`, leaving the portal open for :meth:`resume_execute`.
        Legal only from ``READY``."""
        if self.state is not ProtocolState.READY:
            msg = f"send_bind_execute is only valid in READY (state is {self.state.name})"
            raise ValueError(msg)
        if max_rows < 0:
            msg = f"max_rows must be >= 0 (got {max_rows})"
            raise ValueError(msg)
        self.state = ProtocolState.BUSY
        self._row_description = None
        self._open_portal = portal
        return (
            _builder.build_bind(portal=portal, statement=statement, params=params)
            + _builder.build_execute(portal=portal, max_rows=max_rows)
            + _builder.build_sync()
        )

    def resume_execute(self, *, max_rows: int = 0) -> bytes:
        """Resume a suspended portal: another ``Execute`` → ``Sync`` (the server-side cursor fetch).

        Legal only from ``READY`` after a :class:`PortalSuspendedEvent` left a portal open;
        re-binding is *not* needed — the portal carries its cursor position. ``max_rows`` is the
        next batch size (``0`` drains the rest). Calling it with no open portal is programmer
        misuse (raises :class:`ValueError`)."""
        if self.state is not ProtocolState.READY:
            msg = f"resume_execute is only valid in READY (state is {self.state.name})"
            raise ValueError(msg)
        if self._open_portal is None:
            msg = "resume_execute called with no suspended portal to resume"
            raise ValueError(msg)
        if max_rows < 0:
            msg = f"max_rows must be >= 0 (got {max_rows})"
            raise ValueError(msg)
        self.state = ProtocolState.BUSY
        self._row_description = None
        return (
            _builder.build_execute(portal=self._open_portal, max_rows=max_rows)
            + _builder.build_sync()
        )

    def record_parameter_description(
        self, sql: str, param_oids: Sequence[int], resolved: tuple[int, ...]
    ) -> None:
        """Fold a backend-resolved parameter-OID list into the cache entry, detecting mismatch.

        If a live entry already records *different* resolved OIDs (a type mismatch — e.g. the
        column type changed under a reused SQL string), the entry is invalidated so the next
        :meth:`prepare` is a clean miss and re-prepares against the new types. Otherwise the
        resolved OIDs are stored on the entry."""
        entry = self.cache.get(sql, param_oids)
        if entry is None:
            return
        if entry.resolved_param_oids is not None and entry.resolved_param_oids != resolved:
            self.cache.invalidate(sql, param_oids)
            return
        # Re-store with the resolved OIDs (frozen entries are replaced, not mutated). A refresh
        # of an existing key never evicts (it does not grow the cache), so there is no victim to
        # queue for Close here.
        self.cache.put(
            sql,
            param_oids,
            name=entry.name,
            resolved_param_oids=resolved,
            row_description=entry.row_description,
        )

    def record_row_description(
        self, sql: str, param_oids: Sequence[int], description: RowDescription
    ) -> None:
        """Store the column layout from a ``Describe(statement)`` on the cache entry."""
        entry = self.cache.get(sql, param_oids)
        if entry is None:
            return
        self.cache.put(
            sql,
            param_oids,
            name=entry.name,
            resolved_param_oids=entry.resolved_param_oids,
            row_description=description,
        )

    def seed_row_description(self, description: RowDescription) -> None:
        """Pre-seed the active row layout before ``Execute`` when the server omits ``RowDescription``."""
        self._row_description = description

    def drain_pending_close(self) -> tuple[PreparedStatement, ...]:
        """Return and clear the server-side statements the cache evicted but never closed.

        When :meth:`prepare` stores a plan at capacity, the LRU victim's server-side statement
        (``pelt_stmt_N``) was successfully created by the backend and must be ``Close``\\ d, or it
        leaks until the connection is recycled. The engine queues each victim here rather than
        dropping it silently; the I/O layer (connection / pool) drains this on each round trip
        and issues a ``Close`` per entry. Empty when nothing was evicted. ``Close`` wiring lands
        in E4+; until then this is the explicit leak ledger that makes the orphan observable."""
        if not self._pending_close:
            return ()
        drained = tuple(self._pending_close)
        self._pending_close.clear()
        return drained

    def send_sync(self) -> bytes:
        """A bare ``Sync`` (rarely needed standalone; the batch helpers already append one)."""
        return _builder.build_sync()

    def send_terminate(self) -> bytes:
        """Build a ``Terminate`` and mark the engine CLOSED."""
        self.state = ProtocolState.CLOSED
        return _builder.build_terminate()

    # -- inbound (backend) ---------------------------------------------------
    def receive_bytes(self, data: bytes) -> list[ProtocolEvent]:
        """Append ``data``, drain every complete message, and fold them into events.

        Identical buffering / chunking contract to :meth:`SimpleQueryProtocol.receive_bytes`:
        any chunking reconstructs the same event sequence. Raises :class:`ProtocolError` on a
        malformed frame or a message illegal for the current state."""
        if data:
            self._buffer += data
        events: list[ProtocolEvent] = []
        while True:
            message, consumed = parse_message(memoryview(self._buffer))
            if message is None:
                break
            del self._buffer[:consumed]
            event = self._dispatch(message)
            if event is not None:
                events.append(event)
        return events

    def _dispatch(self, message: PGMessage) -> ProtocolEvent | None:
        # Side-band messages may arrive in any non-closed state and never desync the stream.
        if isinstance(message, ParameterStatus):
            self._require_open(message)
            return ParameterStatusEvent(name=message.name, value=message.value)
        if isinstance(message, NoticeResponse):
            self._require_open(message)
            return NoticeEvent(fields=message.fields)
        if isinstance(message, NotificationResponse):
            self._require_open(message)
            return NotificationEvent(
                pid=message.pid, channel=message.channel, payload=message.payload
            )

        # ReadyForQuery and ErrorResponse close out the current batch.
        if isinstance(message, ReadyForQuery):
            return self._on_ready(message)
        if isinstance(message, ErrorResponse):
            return self._on_error(message)

        # Extended-query result messages are only legal while BUSY.
        if isinstance(message, ParseComplete):
            return self._busy_only(message, ParseCompleteEvent())
        if isinstance(message, BindComplete):
            return self._busy_only(message, BindCompleteEvent())
        if isinstance(message, CloseComplete):
            # The ack of a Close (statement/portal cleanup, e.g. draining drain_pending_close()).
            # It rides in the same Sync-terminated batch, so it is only legal while BUSY; it must
            # never desync — a CloseComplete is always a valid Close acknowledgement.
            return self._busy_only(message, CloseCompleteEvent())
        if isinstance(message, ParameterDescription):
            return self._busy_only(message, ParameterDescriptionEvent(type_oids=message.type_oids))
        if isinstance(message, NoData):
            return self._busy_only(message, NoDataEvent())
        if isinstance(message, RowDescription):
            return self._on_row_description(message)
        if isinstance(message, DataRow):
            return self._on_data_row(message)
        if isinstance(message, CommandComplete):
            return self._on_command_complete(message)
        if isinstance(message, PortalSuspended):
            return self._on_portal_suspended(message)
        if isinstance(message, EmptyQueryResponse):
            return self._busy_only(message, EmptyQueryEvent())

        self._desync(message)

    # -- per-message handlers ------------------------------------------------
    def _on_ready(self, message: ReadyForQuery) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        status = _transaction_status(message.status)
        self.state = ProtocolState.READY
        self.transaction_status = status
        self._row_description = None
        # The batch is fully resynchronized. Any in-flight prepare that reached here without an
        # ErrorResponse succeeded (ParseComplete arrived), so the eagerly-stored entry is valid:
        # clear the in-flight marker. A failed Parse already invalidated the entry in _on_error.
        self._pending_prepare = None
        return ReadyEvent(transaction_status=status)

    def _on_error(self, message: ErrorResponse) -> ProtocolEvent:
        if self.state is ProtocolState.CLOSED:
            self._desync(message)
        # A failed Parse/Bind/Execute closes the open portal; the trailing ReadyForQuery resyncs.
        self._open_portal = None
        # A rejected Parse (bad SQL, missing relation, ...) means the server-side statement was
        # NEVER created, yet prepare() stored the cache entry eagerly. Drop it so the next
        # prepare() of the same (sql, param_oids) is a clean miss that re-Parses, rather than a
        # cache hit that skips the Parse and Binds against a non-existent statement (SQLSTATE
        # 26000 / desync). Cleared either way so it cannot leak into a later batch.
        if self._pending_prepare is not None:
            self.cache.invalidate(*self._pending_prepare)
            self._pending_prepare = None
        return ErrorEvent(error=map_error_response(message))

    def _on_row_description(self, message: RowDescription) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        self._row_description = message
        return RowDescriptionEvent(description=message)

    def _on_data_row(self, message: DataRow) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        if self._row_description is None:
            msg = "DataRow received with no preceding RowDescription"
            raise ProtocolError(msg)
        return DataRowEvent(row=message, description=self._row_description)

    def _on_command_complete(self, message: CommandComplete) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        # The portal is fully drained — clear the resume target.
        self._row_description = None
        self._open_portal = None
        return CommandCompleteEvent(tag=message.tag)

    def _on_portal_suspended(self, message: PortalSuspended) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        # The portal stays open with its cursor position; resume_execute() fetches the next batch.
        # The RowDescription is retained so resumed DataRow batches keep their layout.
        return PortalSuspendedEvent()

    def _busy_only(self, message: PGMessage, event: ProtocolEvent) -> ProtocolEvent:
        if self.state is not ProtocolState.BUSY:
            self._desync(message)
        return event

    # -- desync helpers ------------------------------------------------------
    def _require_open(self, message: PGMessage) -> None:
        if self.state is ProtocolState.CLOSED:
            self._desync(message)

    def _desync(self, message: PGMessage) -> NoReturn:
        msg = (
            f"unexpected {type(message).__name__} in state {self.state.name}: "
            f"connection desynced and must be discarded"
        )
        raise ProtocolError(msg)


__all__ = [
    "AuthOkEvent",
    "AuthRequestEvent",
    "BackendKeyDataEvent",
    "BindCompleteEvent",
    "CloseCompleteEvent",
    "CommandCompleteEvent",
    "DataRowEvent",
    "EmptyQueryEvent",
    "ErrorEvent",
    "ExtendedQueryProtocol",
    "NoDataEvent",
    "NoticeEvent",
    "NotificationEvent",
    "ParameterDescriptionEvent",
    "ParameterStatusEvent",
    "ParseCompleteEvent",
    "PortalSuspendedEvent",
    "PreparedStatement",
    "PreparedStatementCache",
    "ProtocolEvent",
    "ProtocolState",
    "ReadyEvent",
    "RowDescriptionEvent",
    "SimpleQueryProtocol",
    "TransactionStatus",
    "map_error_response",
]
