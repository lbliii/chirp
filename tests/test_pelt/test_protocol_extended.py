"""E3 (#256) — the sans-I/O extended-query protocol: Parse/Bind/Describe/Execute/Sync,
the per-connection prepared-statement cache, and server-side cursors (PortalSuspended).

Backend byte streams are simulated by concatenating framed messages (no socket): the helpers
below mirror the wire layouts in ``_framing`` so the engine sees exactly what Postgres would
send. Live-PG parity is deferred to E4/E6 integration; here we drive the state machine with
hand-built frames and assert the event/state sequence and the cache invariants.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt import _builder
from chirp.data.drivers._pelt._protocol import (
    BindCompleteEvent,
    CloseCompleteEvent,
    CommandCompleteEvent,
    DataRowEvent,
    ErrorEvent,
    ExtendedQueryProtocol,
    NoDataEvent,
    ParameterDescriptionEvent,
    ParseCompleteEvent,
    PortalSuspendedEvent,
    PreparedStatementCache,
    ProtocolState,
    ReadyEvent,
    RowDescriptionEvent,
    TransactionStatus,
)
from chirp.data.drivers._pelt.errors import PostgresError, ProtocolError

# --- wire-frame builders (cf. _framing payload layouts) ---------------------


def _frame(tag: bytes, payload: bytes) -> bytes:
    """tag + Int32(len(payload) + 4) + payload — the backend message frame."""
    return tag + (len(payload) + 4).to_bytes(4, "big") + payload


def _parse_complete() -> bytes:
    # '1' with an empty payload.
    return _frame(b"1", b"")


def _bind_complete() -> bytes:
    # '2' with an empty payload.
    return _frame(b"2", b"")


def _parameter_description(*oids: int) -> bytes:
    # 't' + Int16 count, then Int32 OID per parameter.
    body = len(oids).to_bytes(2, "big")
    for oid in oids:
        body += oid.to_bytes(4, "big")
    return _frame(b"t", body)


def _close_complete() -> bytes:
    # '3' with an empty payload — the backend's ack of a Close request.
    return _frame(b"3", b"")


def _no_data() -> bytes:
    # 'n' with an empty payload.
    return _frame(b"n", b"")


def _portal_suspended() -> bytes:
    # 's' with an empty payload.
    return _frame(b"s", b"")


def _row_description(*columns: tuple[str, int]) -> bytes:
    # 'T' + Int16 field count, then per field:
    #   name C-string, Int32 table OID, Int16 column attr, Int32 type OID,
    #   Int16 type size, Int32 type modifier, Int16 format code.
    body = len(columns).to_bytes(2, "big")
    for name, type_oid in columns:
        body += (
            name.encode()
            + b"\x00"
            + (0).to_bytes(4, "big")  # table OID
            + (0).to_bytes(2, "big")  # column attr
            + type_oid.to_bytes(4, "big")  # type OID
            + (-1).to_bytes(2, "big", signed=True)  # type size (variable)
            + (-1).to_bytes(4, "big", signed=True)  # type modifier
            + (0).to_bytes(2, "big")  # format code (text)
        )
    return _frame(b"T", body)


def _data_row(*values: bytes | None) -> bytes:
    # 'D' + Int16 column count, then per column Int32 length (-1 = NULL) + bytes.
    body = len(values).to_bytes(2, "big")
    for value in values:
        if value is None:
            body += (-1).to_bytes(4, "big", signed=True)
        else:
            body += len(value).to_bytes(4, "big") + value
    return _frame(b"D", body)


def _command_complete(tag: str) -> bytes:
    # 'C' + tag C-string.
    return _frame(b"C", tag.encode() + b"\x00")


def _ready(status: bytes) -> bytes:
    # 'Z' + single status byte ('I' / 'T' / 'E').
    return _frame(b"Z", status)


def _error_response(*fields: tuple[str, str]) -> bytes:
    # 'E' + (1-byte code + value C-string)* + trailing NUL.
    body = b""
    for code, value in fields:
        body += code.encode() + value.encode() + b"\x00"
    body += b"\x00"
    return _frame(b"E", body)


# --- known-vector tests: bit-exact frames -----------------------------------


@pytest.mark.issue(256)
def test_known_vector_parameter_description_two_oids():
    # 't' (0x74) + Int32 length 14 + Int16 count 2 + Int32 23 (int4) + Int32 25 (text).
    expected = (
        b"\x74"
        + b"\x00\x00\x00\x0e"  # length = 14 (4 self + 2 count + 4 + 4)
        + b"\x00\x02"  # 2 parameters
        + b"\x00\x00\x00\x17"  # OID 23 (int4)
        + b"\x00\x00\x00\x19"  # OID 25 (text)
    )
    assert _parameter_description(23, 25) == expected


@pytest.mark.issue(256)
def test_known_vector_parse_and_bind_complete_frames():
    # ParseComplete '1' (0x31) and BindComplete '2' (0x32), both length-4 (empty body).
    assert _parse_complete() == b"\x31\x00\x00\x00\x04"
    assert _bind_complete() == b"\x32\x00\x00\x00\x04"


@pytest.mark.issue(256)
def test_known_vector_portal_suspended_and_no_data_frames():
    # PortalSuspended 's' (0x73) and NoData 'n' (0x6e), both length-4 (empty body).
    assert _portal_suspended() == b"\x73\x00\x00\x00\x04"
    assert _no_data() == b"\x6e\x00\x00\x00\x04"


@pytest.mark.issue(256)
def test_known_vector_parse_describe_outbound_batch():
    # The prepare batch is Parse + Describe(statement) + Sync, exactly as _builder frames them.
    proto = ExtendedQueryProtocol()
    outbound = proto.send_parse_describe(name="pelt_stmt_1", sql="SELECT $1::int", param_oids=(23,))
    assert outbound == (
        _builder.build_parse(name="pelt_stmt_1", query="SELECT $1::int", param_oids=(23,))
        + _builder.build_describe(kind="S", name="pelt_stmt_1")
        + _builder.build_sync()
    )


# --- extended round-trip with params ----------------------------------------


@pytest.mark.issue(256)
def test_prepare_then_execute_round_trip_with_params():
    proto = ExtendedQueryProtocol()
    assert proto.state is ProtocolState.READY

    # PREPARE: Parse + Describe(statement) + Sync.
    statement, outbound = proto.prepare("SELECT id, name FROM t WHERE id = $1", (23,))
    assert outbound is not None
    assert statement.name == "pelt_stmt_1"
    assert proto.state is ProtocolState.BUSY

    reply = (
        _parse_complete()
        + _parameter_description(23)
        + _row_description(("id", 23), ("name", 25))
        + _ready(b"I")
    )
    events = proto.receive_bytes(reply)
    assert [type(e) for e in events] == [
        ParseCompleteEvent,
        ParameterDescriptionEvent,
        RowDescriptionEvent,
        ReadyEvent,
    ]
    pd = events[1]
    assert isinstance(pd, ParameterDescriptionEvent)
    assert pd.type_oids == (23,)
    assert proto.state is ProtocolState.READY

    # Fold the resolved OIDs back into the cache so a future prepare can detect a type drift.
    proto.record_parameter_description("SELECT id, name FROM t WHERE id = $1", (23,), (23,))
    cached = proto.cache.get("SELECT id, name FROM t WHERE id = $1", (23,))
    assert cached is not None
    assert cached.resolved_param_oids == (23,)

    # EXECUTE: Bind + Execute(all rows) + Sync.
    out = proto.send_bind_execute(statement=statement.name, params=(b"1",))
    assert out == (
        _builder.build_bind(portal="", statement=statement.name, params=(b"1",))
        + _builder.build_execute(portal="", max_rows=0)
        + _builder.build_sync()
    )
    assert proto.state is ProtocolState.BUSY

    result = (
        _bind_complete()
        + _row_description(("id", 23), ("name", 25))
        + _data_row(b"1", b"alice")
        + _command_complete("SELECT 1")
        + _ready(b"I")
    )
    events = proto.receive_bytes(result)
    assert [type(e) for e in events] == [
        BindCompleteEvent,
        RowDescriptionEvent,
        DataRowEvent,
        CommandCompleteEvent,
        ReadyEvent,
    ]
    row = events[2]
    assert isinstance(row, DataRowEvent)
    assert row.row.values == (b"1", b"alice")
    assert row.description is events[1].description
    assert proto.state is ProtocolState.READY


@pytest.mark.issue(256)
def test_prepare_cache_hit_skips_wire_traffic():
    proto = ExtendedQueryProtocol()
    statement, outbound = proto.prepare("SELECT 1", ())
    assert outbound is not None
    # Drive the prepare to completion so the engine returns to READY.
    proto.receive_bytes(_parse_complete() + _parameter_description() + _no_data() + _ready(b"I"))
    assert proto.state is ProtocolState.READY

    # Second prepare of the same (sql, param_oids) is a cache hit: no outbound bytes, same name.
    hit, again = proto.prepare("SELECT 1", ())
    assert again is None
    assert hit.name == statement.name
    # A hit must not move the engine off READY (no batch was sent).
    assert proto.state is ProtocolState.READY


@pytest.mark.issue(256)
def test_describe_no_data_for_non_returning_statement():
    proto = ExtendedQueryProtocol()
    proto.prepare("INSERT INTO t (n) VALUES ($1)", (23,))
    events = proto.receive_bytes(
        _parse_complete() + _parameter_description(23) + _no_data() + _ready(b"I")
    )
    assert [type(e) for e in events] == [
        ParseCompleteEvent,
        ParameterDescriptionEvent,
        NoDataEvent,
        ReadyEvent,
    ]
    assert proto.state is ProtocolState.READY


@pytest.mark.issue(256)
def test_close_complete_is_surfaced_not_desynced():
    # CloseComplete (tag '3') is the backend's ack of a Close request — it rides in the same
    # Sync-terminated batch (e.g. closing the orphaned statements drain_pending_close() surfaces).
    # _framing parses it, so the engine MUST handle it: surface a CloseCompleteEvent rather than
    # raise ProtocolError on an otherwise-legal Close acknowledgement.
    proto = ExtendedQueryProtocol()
    statement, _ = proto.prepare("SELECT 1", ())
    proto.receive_bytes(_parse_complete() + _parameter_description() + _no_data() + _ready(b"I"))
    assert proto.state is ProtocolState.READY

    # A batch that runs the statement and then closes it: Bind/Execute results, then the Close
    # ack, then the resync ReadyForQuery. The CloseComplete must not desync.
    proto.send_bind_execute(statement=statement.name)
    batch = (
        _bind_complete()
        + _row_description(("c", 23))
        + _data_row(b"1")
        + _command_complete("SELECT 1")
        + _close_complete()
        + _ready(b"I")
    )
    events = proto.receive_bytes(batch)
    assert [type(e) for e in events] == [
        BindCompleteEvent,
        RowDescriptionEvent,
        DataRowEvent,
        CommandCompleteEvent,
        CloseCompleteEvent,
        ReadyEvent,
    ]
    # The ack does not knock the engine off the normal resync path.
    assert proto.state is ProtocolState.READY


@pytest.mark.issue(256)
def test_close_complete_while_ready_is_desync():
    # CloseComplete is still a BUSY-only message: arriving with no batch in flight is a desync,
    # consistent with ParseComplete/BindComplete. It is surfaced-not-raised only mid-batch.
    proto = ExtendedQueryProtocol()
    with pytest.raises(ProtocolError, match=r"CloseComplete.*READY"):
        proto.receive_bytes(_close_complete())


# --- cache: hit vs miss, eviction, version / type mismatch ------------------


@pytest.mark.issue(256)
def test_cache_hit_vs_miss_by_key():
    cache = PreparedStatementCache(size=4)
    assert cache.get("SELECT 1") is None  # cold miss

    name = cache.next_statement_name()
    cache.put("SELECT 1", (), name=name)
    hit = cache.get("SELECT 1")
    assert hit is not None
    assert hit.name == name

    # Same SQL but a different explicit param-OID list is a DISTINCT key → a miss.
    assert cache.get("SELECT 1", (23,)) is None
    # A different SQL is also a miss.
    assert cache.get("SELECT 2") is None


@pytest.mark.issue(256)
def test_cache_disabled_when_size_zero():
    cache = PreparedStatementCache(size=0)
    assert cache.put("SELECT 1", (), name="x") is None
    assert cache.get("SELECT 1") is None
    assert len(cache) == 0


@pytest.mark.issue(256)
def test_cache_lru_eviction_at_capacity():
    cache = PreparedStatementCache(size=2)
    cache.put("a", (), name=cache.next_statement_name())
    cache.put("b", (), name=cache.next_statement_name())
    assert len(cache) == 2

    # Touch "a" so it becomes most-recently-used; "b" is now the LRU victim.
    assert cache.get("a") is not None

    evicted = cache.put("c", (), name=cache.next_statement_name())
    assert evicted is not None
    assert evicted.sql == "b"  # the untouched, least-recently-used entry was evicted
    assert len(cache) == 2
    assert cache.get("b") is None  # gone
    assert cache.get("a") is not None  # survived
    assert cache.get("c") is not None  # newest


@pytest.mark.issue(256)
def test_prepare_at_capacity_reports_evicted_statement_for_close():
    # An LRU eviction in prepare() must SURFACE the orphaned server-side statement so the I/O
    # layer can Close it — dropping it silently leaks a backend prepared statement (pelt_stmt_N)
    # until the connection is recycled. drain_pending_close() is the ledger.
    proto = ExtendedQueryProtocol(cache=PreparedStatementCache(size=1))

    def drive_prepare(sql: str) -> None:
        proto.prepare(sql, ())
        proto.receive_bytes(
            _parse_complete() + _parameter_description() + _no_data() + _ready(b"I")
        )
        assert proto.state is ProtocolState.READY

    drive_prepare("SELECT 1")
    first = proto.cache.get("SELECT 1", ())
    assert first is not None
    assert first.name == "pelt_stmt_1"
    # Nothing evicted yet.
    assert proto.drain_pending_close() == ()

    # A second prepare at size-1 capacity evicts the first statement.
    drive_prepare("SELECT 2")
    orphans = proto.drain_pending_close()
    assert len(orphans) == 1
    assert orphans[0].name == "pelt_stmt_1"
    assert orphans[0].sql == "SELECT 1"
    # Draining is destructive: the ledger is empty afterward (no double-Close).
    assert proto.drain_pending_close() == ()
    # The surviving plan is the most recent one.
    assert proto.cache.get("SELECT 2", ()) is not None
    assert proto.cache.get("SELECT 1", ()) is None


@pytest.mark.issue(256)
def test_prepare_without_eviction_has_empty_close_ledger():
    # A prepare that does not hit capacity evicts nothing — the close ledger stays empty.
    proto = ExtendedQueryProtocol(cache=PreparedStatementCache(size=4))
    proto.prepare("SELECT 1", ())
    proto.receive_bytes(_parse_complete() + _parameter_description() + _no_data() + _ready(b"I"))
    assert proto.drain_pending_close() == ()


@pytest.mark.issue(256)
def test_cache_version_bump_is_clean_miss_not_stale_reuse():
    cache = PreparedStatementCache(size=4)
    cache.put("SELECT * FROM t", (), name="pelt_stmt_1")
    assert cache.get("SELECT * FROM t") is not None

    # A schema change advances the generation; the stale entry is a clean miss (re-prepare),
    # never a reused stale plan.
    new_version = cache.bump_version()
    assert new_version == 1
    assert cache.get("SELECT * FROM t") is None
    # The stale entry was evicted on the missed lookup.
    assert len(cache) == 0

    # Re-prepared entries are stamped with the new generation and hit again.
    cache.put("SELECT * FROM t", (), name="pelt_stmt_2")
    fresh = cache.get("SELECT * FROM t")
    assert fresh is not None
    assert fresh.version == 1
    assert fresh.name == "pelt_stmt_2"


@pytest.mark.issue(256)
def test_type_mismatch_on_resolve_is_clean_miss():
    proto = ExtendedQueryProtocol()
    sql = "SELECT $1"
    proto.prepare(sql, ())  # server infers the type
    proto.receive_bytes(_parse_complete() + _parameter_description(23) + _no_data() + _ready(b"I"))
    # First resolve: server inferred int4 (OID 23).
    proto.record_parameter_description(sql, (), (23,))
    entry = proto.cache.get(sql, ())
    assert entry is not None
    assert entry.resolved_param_oids == (23,)

    # A later resolve reports a DIFFERENT type (e.g. the column was altered to int8/OID 20):
    # this is a type mismatch, so the plan is invalidated rather than reused.
    proto.record_parameter_description(sql, (), (20,))
    assert proto.cache.get(sql, ()) is None  # clean miss → next prepare re-prepares


@pytest.mark.issue(256)
def test_negative_cache_size_is_programmer_misuse():
    with pytest.raises(ValueError, match="statement_cache_size must be >= 0"):
        PreparedStatementCache(size=-1)


@pytest.mark.issue(256)
def test_statement_names_are_stable_and_unique():
    cache = PreparedStatementCache(size=4)
    names = [cache.next_statement_name() for _ in range(3)]
    assert names == ["pelt_stmt_1", "pelt_stmt_2", "pelt_stmt_3"]
    assert len(set(names)) == 3


# --- server-side cursor: PortalSuspended → resume ---------------------------


@pytest.mark.issue(256, 260)
def test_portal_suspended_then_resumed_execute():
    proto = ExtendedQueryProtocol()
    statement, _ = proto.prepare("SELECT n FROM big", ())
    proto.receive_bytes(
        _parse_complete() + _parameter_description() + _row_description(("n", 23)) + _ready(b"I")
    )
    assert proto.state is ProtocolState.READY

    # First batch: Bind + Execute(max_rows=2) + Sync → 2 rows then PortalSuspended.
    out = proto.send_bind_execute(statement=statement.name, max_rows=2)
    assert out == (
        _builder.build_bind(portal="", statement=statement.name, params=())
        + _builder.build_execute(portal="", max_rows=2)
        + _builder.build_sync()
    )
    description = _row_description(("n", 23))
    batch1 = (
        _bind_complete()
        + description
        + _data_row(b"1")
        + _data_row(b"2")
        + _portal_suspended()
        + _ready(b"I")
    )
    events = proto.receive_bytes(batch1)
    assert [type(e) for e in events] == [
        BindCompleteEvent,
        RowDescriptionEvent,
        DataRowEvent,
        DataRowEvent,
        PortalSuspendedEvent,
        ReadyEvent,
    ]
    assert proto.state is ProtocolState.READY

    # RESUME: another Execute on the same open portal (no re-Bind) → the rest, then complete.
    # PostgreSQL does not send another RowDescription for a resumed portal, so the connection
    # restores the prepared statement's known layout before asking the protocol to resume.
    row_description = next(
        event.description for event in events if isinstance(event, RowDescriptionEvent)
    )
    proto.seed_row_description(row_description)
    resume = proto.resume_execute(max_rows=2)
    assert resume == (_builder.build_execute(portal="", max_rows=2) + _builder.build_sync())
    assert proto.state is ProtocolState.BUSY

    batch2 = _data_row(b"3") + _command_complete("SELECT 3") + _ready(b"I")
    events = proto.receive_bytes(batch2)
    assert [type(e) for e in events] == [
        DataRowEvent,
        CommandCompleteEvent,
        ReadyEvent,
    ]
    assert proto.state is ProtocolState.READY


@pytest.mark.issue(256)
def test_resume_without_suspended_portal_is_programmer_misuse():
    proto = ExtendedQueryProtocol()
    with pytest.raises(ValueError, match="no suspended portal"):
        proto.resume_execute()


@pytest.mark.issue(256)
def test_command_complete_clears_resume_target():
    proto = ExtendedQueryProtocol()
    statement, _ = proto.prepare("SELECT 1", ())
    proto.receive_bytes(_parse_complete() + _parameter_description() + _no_data() + _ready(b"I"))
    proto.send_bind_execute(statement=statement.name, max_rows=2)
    # The portal drains fully (CommandComplete, not PortalSuspended) → nothing to resume.
    proto.receive_bytes(
        _bind_complete()
        + _row_description(("c", 23))
        + _data_row(b"1")
        + _command_complete("SELECT 1")
        + _ready(b"I")
    )
    with pytest.raises(ValueError, match="no suspended portal"):
        proto.resume_execute()


@pytest.mark.issue(256)
def test_negative_max_rows_is_programmer_misuse():
    proto = ExtendedQueryProtocol()
    statement, _ = proto.prepare("SELECT 1", ())
    proto.receive_bytes(_parse_complete() + _parameter_description() + _no_data() + _ready(b"I"))
    with pytest.raises(ValueError, match="max_rows must be >= 0"):
        proto.send_bind_execute(statement=statement.name, max_rows=-1)


# --- error handling within the extended batch -------------------------------


@pytest.mark.issue(256)
def test_error_during_bind_resyncs_and_clears_portal():
    proto = ExtendedQueryProtocol()
    statement, _ = proto.prepare("SELECT $1", (23,))
    proto.receive_bytes(_parse_complete() + _parameter_description(23) + _no_data() + _ready(b"I"))
    # Bad bind value → ErrorResponse, then the trailing ReadyForQuery resynchronizes.
    proto.send_bind_execute(statement=statement.name, params=(b"not-an-int",))
    stream = _error_response(
        ("S", "ERROR"),
        ("V", "ERROR"),
        ("C", "22P02"),
        ("M", "invalid input syntax for type integer"),
        ("H", "use a valid integer literal"),
    ) + _ready(b"E")
    events = proto.receive_bytes(stream)
    assert [type(e) for e in events] == [ErrorEvent, ReadyEvent]
    err_event = events[0]
    assert isinstance(err_event, ErrorEvent)
    err = err_event.error
    assert isinstance(err, PostgresError)
    assert err.sqlstate == "22P02"
    assert err.code == "PELT_PG_22P02"
    assert err.hint == "use a valid integer literal"

    # The failed transaction is reflected; the connection is reusable after the ReadyForQuery.
    ready = events[1]
    assert isinstance(ready, ReadyEvent)
    assert ready.transaction_status is TransactionStatus.IN_FAILED_TRANSACTION
    assert proto.state is ProtocolState.READY
    # The portal was cleared, so there is nothing to (wrongly) resume.
    with pytest.raises(ValueError, match="no suspended portal"):
        proto.resume_execute()


@pytest.mark.issue(256)
def test_error_during_parse_invalidates_cache_entry():
    # prepare() stores the cache entry eagerly, BEFORE the backend accepts the Parse. If the
    # Parse is rejected (bad SQL, missing relation, ...), the server-side statement was never
    # created — so the eager entry MUST be invalidated, or the next prepare() of the same SQL is
    # a cache hit that skips the re-Parse and Binds against a statement that does not exist
    # (SQLSTATE 26000 / desync). This covers the Parse phase; test_error_during_bind covers Bind.
    proto = ExtendedQueryProtocol()
    sql = "SELECT * FROM does_not_exist"
    statement, outbound = proto.prepare(sql, ())
    assert outbound is not None
    assert statement.name == "pelt_stmt_1"
    # The entry is provisionally cached while the Parse is in flight.
    assert proto.cache.get(sql, ()) is not None
    assert proto.state is ProtocolState.BUSY

    # The backend rejects the Parse: ErrorResponse (42P01) then the resync ReadyForQuery.
    stream = _error_response(
        ("S", "ERROR"),
        ("V", "ERROR"),
        ("C", "42P01"),
        ("M", 'relation "does_not_exist" does not exist'),
        ("H", "check the table name"),
    ) + _ready(b"E")
    events = proto.receive_bytes(stream)
    assert [type(e) for e in events] == [ErrorEvent, ReadyEvent]
    err_event = events[0]
    assert isinstance(err_event, ErrorEvent)
    assert isinstance(err_event.error, PostgresError)
    assert err_event.error.sqlstate == "42P01"
    assert proto.state is ProtocolState.READY

    # The never-created entry was dropped: the next prepare() is a clean MISS that re-Parses
    # (outbound is not None and a fresh statement name is generated).
    assert proto.cache.get(sql, ()) is None
    statement2, outbound2 = proto.prepare(sql, ())
    assert outbound2 is not None
    assert statement2.name == "pelt_stmt_2"  # a new server-side name, never aliasing the failed one


@pytest.mark.issue(256)
def test_successful_prepare_does_not_invalidate_on_later_unrelated_error():
    # A clean Parse must NOT have its cache entry dropped by a *subsequent* Bind/Execute error:
    # only a Parse rejection invalidates. Guards against over-eager _pending_prepare clearing.
    proto = ExtendedQueryProtocol()
    sql = "SELECT $1"
    statement, _ = proto.prepare(sql, (23,))
    proto.receive_bytes(_parse_complete() + _parameter_description(23) + _no_data() + _ready(b"I"))
    # The plan is live after a successful Parse.
    assert proto.cache.get(sql, (23,)) is not None

    # A later Bind/Execute fails (bad value) — the prepared statement itself is still valid.
    proto.send_bind_execute(statement=statement.name, params=(b"not-an-int",))
    proto.receive_bytes(
        _error_response(("S", "ERROR"), ("V", "ERROR"), ("C", "22P02"), ("M", "bad int"))
        + _ready(b"E")
    )
    # The cached plan survives the execute-phase error: a re-prepare is a HIT (no re-Parse).
    hit, outbound = proto.prepare(sql, (23,))
    assert outbound is None
    assert hit.name == statement.name


# --- desync discipline ------------------------------------------------------


@pytest.mark.issue(256)
def test_data_row_while_ready_is_desync():
    proto = ExtendedQueryProtocol()
    with pytest.raises(ProtocolError, match=r"DataRow.*READY"):
        proto.receive_bytes(_data_row(b"1"))


@pytest.mark.issue(256)
def test_data_row_without_row_description_is_desync():
    proto = ExtendedQueryProtocol()
    statement, _ = proto.prepare("SELECT 1", ())
    proto.receive_bytes(_parse_complete() + _parameter_description() + _no_data() + _ready(b"I"))
    proto.send_bind_execute(statement=statement.name)
    with pytest.raises(ProtocolError, match="no preceding RowDescription"):
        proto.receive_bytes(_bind_complete() + _data_row(b"1"))


@pytest.mark.issue(256)
def test_ready_while_already_ready_is_desync():
    proto = ExtendedQueryProtocol()
    with pytest.raises(ProtocolError, match=r"ReadyForQuery.*READY"):
        proto.receive_bytes(_ready(b"I"))


@pytest.mark.issue(256)
def test_parse_describe_while_busy_is_programmer_misuse():
    proto = ExtendedQueryProtocol()
    proto.prepare("SELECT 1", ())  # now BUSY
    with pytest.raises(ValueError, match="only valid in READY"):
        proto.send_parse_describe(name="x", sql="SELECT 2")


@pytest.mark.issue(256)
def test_terminate_closes_engine_and_then_messages_desync():
    proto = ExtendedQueryProtocol()
    assert proto.send_terminate() == _builder.build_terminate()
    assert proto.state is ProtocolState.CLOSED
    with pytest.raises(ProtocolError, match=r"ParseComplete.*CLOSED"):
        proto.receive_bytes(_parse_complete())


# --- byte-at-a-time / arbitrary chunking is invariant -----------------------


@pytest.mark.issue(256)
def test_byte_at_a_time_matches_bulk_feed():
    reply = (
        _parse_complete()
        + _parameter_description(23, 25)
        + _row_description(("id", 23), ("name", 25))
        + _ready(b"I")
    )

    bulk = ExtendedQueryProtocol()
    bulk.send_parse_describe(name="s1", sql="SELECT id, name FROM t WHERE id=$1", param_oids=(23,))
    bulk_events = bulk.receive_bytes(reply)

    drip = ExtendedQueryProtocol()
    drip.send_parse_describe(name="s1", sql="SELECT id, name FROM t WHERE id=$1", param_oids=(23,))
    drip_events = []
    for i in range(len(reply)):
        drip_events.extend(drip.receive_bytes(reply[i : i + 1]))

    assert drip_events == bulk_events
    assert drip.state is bulk.state is ProtocolState.READY


@pytest.mark.issue(256)
@given(chunk_size=st.integers(min_value=1, max_value=64))
def test_arbitrary_chunking_is_invariant(chunk_size):
    reply = (
        _bind_complete()
        + _row_description(("a", 23), ("b", 25))
        + _data_row(b"1", b"x")
        + _data_row(b"2", None)
        + _portal_suspended()
        + _ready(b"I")
    )

    def feed(proto: ExtendedQueryProtocol, data: bytes, chunk: int) -> list[type]:
        events: list[type] = []
        for offset in range(0, len(data), chunk):
            events.extend(type(ev) for ev in proto.receive_bytes(data[offset : offset + chunk]))
        return events

    def run(chunk: int) -> list[type]:
        proto = ExtendedQueryProtocol()
        proto.send_bind_execute(statement="s1", params=(), max_rows=2)
        return feed(proto, reply, chunk)

    assert run(chunk_size) == run(1)


# --- round-trip property: param OIDs survive a Parse → ParameterDescription -


@pytest.mark.issue(256)
@given(
    oids=st.lists(st.integers(min_value=0, max_value=2**31 - 1), min_size=0, max_size=8),
)
def test_parameter_description_round_trip(oids):
    proto = ExtendedQueryProtocol()
    proto.send_parse_describe(name="s", sql="SELECT 1", param_oids=tuple(oids))
    events = proto.receive_bytes(
        _parse_complete() + _parameter_description(*oids) + _no_data() + _ready(b"I")
    )
    pd = events[1]
    assert isinstance(pd, ParameterDescriptionEvent)
    assert pd.type_oids == tuple(oids)
