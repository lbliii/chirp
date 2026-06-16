"""E3 (#256) — the sans-I/O simple-query protocol state machine.

Backend byte streams are simulated by concatenating framed messages (no socket): the helpers
below mirror the wire layouts in ``_framing`` so the engine sees exactly what Postgres would
send. Live-PG parity is deferred to E4/E6 integration; here we drive the state machine with
hand-built frames and assert the event/state sequence.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt import _builder
from chirp.data.drivers._pelt._protocol import (
    AuthOkEvent,
    BackendKeyDataEvent,
    CommandCompleteEvent,
    DataRowEvent,
    EmptyQueryEvent,
    ErrorEvent,
    NoticeEvent,
    NotificationEvent,
    ParameterStatusEvent,
    ProtocolState,
    ReadyEvent,
    RowDescriptionEvent,
    SimpleQueryProtocol,
    TransactionStatus,
    map_error_response,
)
from chirp.data.drivers._pelt.errors import PostgresError, ProtocolError

# --- wire-frame builders (cf. _framing payload layouts) ---------------------


def _frame(tag: bytes, payload: bytes) -> bytes:
    """tag + Int32(len(payload) + 4) + payload — the backend message frame."""
    return tag + (len(payload) + 4).to_bytes(4, "big") + payload


def _auth_ok() -> bytes:
    # 'R' + Int32 sub-type 0 (AuthenticationOk).
    return _frame(b"R", (0).to_bytes(4, "big"))


def _ready(status: bytes) -> bytes:
    # 'Z' + single status byte ('I' / 'T' / 'E').
    return _frame(b"Z", status)


def _parameter_status(name: str, value: str) -> bytes:
    # 'S' + name C-string + value C-string.
    return _frame(b"S", name.encode() + b"\x00" + value.encode() + b"\x00")


def _backend_key_data(pid: int, secret: int) -> bytes:
    # 'K' + Int32 pid + Int32 secret.
    return _frame(b"K", pid.to_bytes(4, "big") + secret.to_bytes(4, "big"))


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


def _empty_query() -> bytes:
    # 'I' with an empty payload.
    return _frame(b"I", b"")


def _error_response(*fields: tuple[str, str]) -> bytes:
    # 'E' + (1-byte code + value C-string)* + trailing NUL.
    body = b""
    for code, value in fields:
        body += code.encode() + value.encode() + b"\x00"
    body += b"\x00"
    return _frame(b"E", body)


def _notice_response(*fields: tuple[str, str]) -> bytes:
    body = b""
    for code, value in fields:
        body += code.encode() + value.encode() + b"\x00"
    body += b"\x00"
    return _frame(b"N", body)


def _notification(pid: int, channel: str, payload: str) -> bytes:
    # 'A' + Int32 pid + channel C-string + payload C-string.
    body = pid.to_bytes(4, "big") + channel.encode() + b"\x00" + payload.encode() + b"\x00"
    return _frame(b"A", body)


def _at_ready() -> SimpleQueryProtocol:
    """A fresh engine driven through startup → auth-ok → ReadyForQuery(idle)."""
    proto = SimpleQueryProtocol()
    proto.send_startup(user="alice", database="db")
    proto.receive_bytes(_auth_ok() + _ready(b"I"))
    assert proto.state is ProtocolState.READY
    return proto


# --- known-vector tests: bit-exact frames -----------------------------------


@pytest.mark.issue(256)
def test_known_vector_ready_for_query_idle():
    # 'Z' (0x5a) + Int32 length 5 (0x00000005) + status 'I' (0x49).
    assert _ready(b"I") == b"\x5a\x00\x00\x00\x05\x49"
    proto = SimpleQueryProtocol()
    proto.send_startup(user="u")
    [auth, ready] = proto.receive_bytes(_auth_ok() + _ready(b"I"))
    assert isinstance(auth, AuthOkEvent)
    assert isinstance(ready, ReadyEvent)
    assert ready.transaction_status is TransactionStatus.IDLE


@pytest.mark.issue(256)
def test_known_vector_auth_ok_frame():
    # 'R' (0x52) + Int32 length 8 (0x00000008) + Int32 sub-type 0 (0x00000000).
    assert _auth_ok() == b"\x52\x00\x00\x00\x08\x00\x00\x00\x00"


@pytest.mark.issue(256)
def test_known_vector_data_row_with_null():
    # 'D' (0x44) + Int32 length 16 + Int16 count 2 + (Int32 2 + b"42") + (Int32 -1 = NULL).
    expected = (
        b"\x44"
        + b"\x00\x00\x00\x10"  # length = 16 (4 self + 2 count + 6 first col + 4 null col)
        + b"\x00\x02"  # 2 columns
        + b"\x00\x00\x00\x02"  # first value length 2
        + b"42"
        + b"\xff\xff\xff\xff"  # second value length -1 → NULL
    )
    assert _data_row(b"42", None) == expected


@pytest.mark.issue(256)
def test_known_vector_command_complete_frame():
    # 'C' (0x43) + Int32 length 13 + "SELECT 2\x00".
    assert _command_complete("SELECT 2") == b"\x43\x00\x00\x00\x0dSELECT 2\x00"


# --- lifecycle: auth-ok → ready ---------------------------------------------


@pytest.mark.issue(256)
def test_startup_to_ready_sequence():
    proto = SimpleQueryProtocol()
    assert proto.state is ProtocolState.STARTUP
    outbound = proto.send_startup(user="alice", database="db", application_name="pelt")
    assert outbound == _builder.build_startup(user="alice", database="db", application_name="pelt")
    assert proto.state is ProtocolState.AUTHENTICATING

    stream = (
        _auth_ok()
        + _parameter_status("server_version", "17.0")
        + _backend_key_data(1234, 5678)
        + _ready(b"I")
    )
    events = proto.receive_bytes(stream)
    assert [type(e) for e in events] == [
        AuthOkEvent,
        ParameterStatusEvent,
        BackendKeyDataEvent,
        ReadyEvent,
    ]
    assert events[1] == ParameterStatusEvent(name="server_version", value="17.0")
    assert events[2] == BackendKeyDataEvent(pid=1234, secret_key=5678)
    assert proto.backend_pid == 1234
    assert proto.backend_secret_key == 5678
    assert proto.state is ProtocolState.READY
    assert proto.transaction_status is TransactionStatus.IDLE


@pytest.mark.issue(256)
def test_send_startup_twice_is_programmer_misuse():
    proto = SimpleQueryProtocol()
    proto.send_startup(user="u")
    with pytest.raises(ValueError, match="only valid in STARTUP"):
        proto.send_startup(user="u")


# --- simple query: SELECT returning 2 rows ----------------------------------


@pytest.mark.issue(256)
def test_select_two_rows():
    proto = _at_ready()
    outbound = proto.send_query("SELECT id, name FROM t")
    assert outbound == _builder.build_query("SELECT id, name FROM t")
    assert proto.state is ProtocolState.BUSY

    stream = (
        _row_description(("id", 23), ("name", 25))
        + _data_row(b"1", b"alice")
        + _data_row(b"2", None)
        + _command_complete("SELECT 2")
        + _ready(b"I")
    )
    events = proto.receive_bytes(stream)
    assert [type(e) for e in events] == [
        RowDescriptionEvent,
        DataRowEvent,
        DataRowEvent,
        CommandCompleteEvent,
        ReadyEvent,
    ]

    rd, r1, r2, cc, ready = events
    assert isinstance(rd, RowDescriptionEvent)
    assert tuple(f.name for f in rd.description.fields) == ("id", "name")

    assert isinstance(r1, DataRowEvent)
    assert r1.row.values == (b"1", b"alice")
    # Each row carries the layout it belongs to (raw bytes; decoding is the next layer).
    assert r1.description is rd.description
    assert isinstance(r2, DataRowEvent)
    assert r2.row.values == (b"2", None)

    assert isinstance(cc, CommandCompleteEvent)
    assert cc.tag == "SELECT 2"
    assert isinstance(ready, ReadyEvent)
    assert proto.state is ProtocolState.READY

    # READY again: another query is accepted.
    assert proto.send_query("SELECT 1") == _builder.build_query("SELECT 1")


@pytest.mark.issue(256)
def test_in_transaction_status_tracked():
    proto = _at_ready()
    proto.send_query("BEGIN")
    events = proto.receive_bytes(_command_complete("BEGIN") + _ready(b"T"))
    ready = events[-1]
    assert isinstance(ready, ReadyEvent)
    assert ready.transaction_status is TransactionStatus.IN_TRANSACTION
    assert proto.transaction_status is TransactionStatus.IN_TRANSACTION


# --- empty query ------------------------------------------------------------


@pytest.mark.issue(256)
def test_empty_query():
    proto = _at_ready()
    proto.send_query("")
    events = proto.receive_bytes(_empty_query() + _ready(b"I"))
    assert [type(e) for e in events] == [EmptyQueryEvent, ReadyEvent]
    assert proto.state is ProtocolState.READY


# --- error mapping ----------------------------------------------------------


@pytest.mark.issue(256)
def test_error_response_maps_to_postgres_error():
    proto = _at_ready()
    proto.send_query("SELECT * FROM missing")
    stream = _error_response(
        ("S", "ERROR"),
        ("V", "ERROR"),
        ("C", "42P01"),
        ("M", 'relation "missing" does not exist'),
        ("H", "check the table name"),
    ) + _ready(b"I")
    events = proto.receive_bytes(stream)
    assert [type(e) for e in events] == [ErrorEvent, ReadyEvent]

    err_event = events[0]
    assert isinstance(err_event, ErrorEvent)
    err = err_event.error
    assert isinstance(err, PostgresError)
    assert err.sqlstate == "42P01"
    assert err.code == "PELT_PG_42P01"
    assert err.severity == "ERROR"
    assert err.hint == "check the table name"
    assert str(err) == 'relation "missing" does not exist'

    # The trailing ReadyForQuery resynchronizes — the connection is reusable.
    assert proto.state is ProtocolState.READY


@pytest.mark.issue(256)
def test_map_error_response_helper():
    from chirp.data.drivers._pelt._messages import ErrorResponse

    error = ErrorResponse(
        fields=(("V", "FATAL"), ("C", "28000"), ("M", "auth failed"), ("D", "wrong password"))
    )
    mapped = map_error_response(error)
    assert mapped.sqlstate == "28000"
    assert mapped.severity == "FATAL"
    assert mapped.detail == "wrong password"


# --- side-band messages -----------------------------------------------------


@pytest.mark.issue(256)
def test_side_band_messages_mid_query_do_not_desync():
    proto = _at_ready()
    proto.send_query("SELECT 1")
    # A NoticeResponse, ParameterStatus, and NotificationResponse can arrive mid-result.
    stream = (
        _row_description(("n", 23))
        + _notice_response(("S", "NOTICE"), ("M", "heads up"))
        + _data_row(b"1")
        + _parameter_status("application_name", "pelt")
        + _notification(99, "chan", "payload")
        + _command_complete("SELECT 1")
        + _ready(b"I")
    )
    events = proto.receive_bytes(stream)
    assert [type(e) for e in events] == [
        RowDescriptionEvent,
        NoticeEvent,
        DataRowEvent,
        ParameterStatusEvent,
        NotificationEvent,
        CommandCompleteEvent,
        ReadyEvent,
    ]
    notice = events[1]
    assert isinstance(notice, NoticeEvent)
    assert ("M", "heads up") in notice.fields
    notif = events[4]
    assert isinstance(notif, NotificationEvent)
    assert notif == NotificationEvent(pid=99, channel="chan", payload="payload")
    assert proto.state is ProtocolState.READY


# --- byte-at-a-time feeding reconstructs identically ------------------------


@pytest.mark.issue(256)
def test_byte_at_a_time_matches_bulk_feed():
    stream = (
        _auth_ok()
        + _parameter_status("server_version", "17.0")
        + _backend_key_data(1, 2)
        + _ready(b"I")
    )

    bulk = SimpleQueryProtocol()
    bulk.send_startup(user="u")
    bulk_events = bulk.receive_bytes(stream)

    drip = SimpleQueryProtocol()
    drip.send_startup(user="u")
    drip_events = []
    for i in range(len(stream)):
        drip_events.extend(drip.receive_bytes(stream[i : i + 1]))

    assert drip_events == bulk_events
    assert drip.state is bulk.state is ProtocolState.READY
    assert drip.backend_pid == bulk.backend_pid == 1


@pytest.mark.issue(256)
def test_byte_at_a_time_query_results():
    proto = SimpleQueryProtocol()
    proto.send_startup(user="u")
    proto.receive_bytes(_auth_ok() + _ready(b"I"))
    proto.send_query("SELECT id FROM t")

    stream = (
        _row_description(("id", 23))
        + _data_row(b"7")
        + _data_row(None)
        + _command_complete("SELECT 2")
        + _ready(b"I")
    )
    events = []
    for i in range(len(stream)):
        events.extend(proto.receive_bytes(stream[i : i + 1]))

    assert [type(e) for e in events] == [
        RowDescriptionEvent,
        DataRowEvent,
        DataRowEvent,
        CommandCompleteEvent,
        ReadyEvent,
    ]
    rows = [e for e in events if isinstance(e, DataRowEvent)]
    assert [r.row.values for r in rows] == [(b"7",), (None,)]
    assert proto.state is ProtocolState.READY


@pytest.mark.issue(256)
@given(chunk_size=st.integers(min_value=1, max_value=64))
def test_arbitrary_chunking_is_invariant(chunk_size):
    # Two backend phases with a frontend send_query() in between, mirroring the real I/O
    # loop: the result frames only arrive (and are only legal) after the query is sent.
    setup = _auth_ok() + _ready(b"I")
    result = (
        _row_description(("a", 23), ("b", 25))
        + _data_row(b"1", b"x")
        + _data_row(b"2", None)
        + _command_complete("SELECT 2")
        + _ready(b"I")
    )

    def feed(proto: SimpleQueryProtocol, data: bytes, chunk: int) -> list[type]:
        events: list[type] = []
        for offset in range(0, len(data), chunk):
            events.extend(type(ev) for ev in proto.receive_bytes(data[offset : offset + chunk]))
        return events

    def run(chunk: int) -> list[type]:
        proto = SimpleQueryProtocol()
        proto.send_startup(user="u")
        events = feed(proto, setup, chunk)
        proto.send_query("SELECT a, b FROM t")
        events += feed(proto, result, chunk)
        return events

    assert run(chunk_size) == run(1)


# --- desync discipline ------------------------------------------------------


@pytest.mark.issue(256)
def test_data_row_before_ready_is_desync():
    # A DataRow while still AUTHENTICATING is illegal.
    proto = SimpleQueryProtocol()
    proto.send_startup(user="u")
    with pytest.raises(ProtocolError, match=r"DataRow.*AUTHENTICATING"):
        proto.receive_bytes(_data_row(b"1"))


@pytest.mark.issue(256)
def test_command_complete_while_ready_is_desync():
    proto = _at_ready()
    with pytest.raises(ProtocolError, match=r"CommandComplete.*READY"):
        proto.receive_bytes(_command_complete("SELECT 1"))


@pytest.mark.issue(256)
def test_data_row_without_row_description_is_desync():
    proto = _at_ready()
    proto.send_query("SELECT 1")
    with pytest.raises(ProtocolError, match="no preceding RowDescription"):
        proto.receive_bytes(_data_row(b"1"))


@pytest.mark.issue(256)
def test_ready_while_already_ready_is_desync():
    proto = _at_ready()
    with pytest.raises(ProtocolError, match=r"ReadyForQuery.*READY"):
        proto.receive_bytes(_ready(b"I"))


@pytest.mark.issue(256)
def test_unknown_transaction_status_raises():
    proto = SimpleQueryProtocol()
    proto.send_startup(user="u")
    proto.receive_bytes(_auth_ok())
    with pytest.raises(ProtocolError, match="transaction status"):
        proto.receive_bytes(_ready(b"X"))


@pytest.mark.issue(256)
def test_send_query_before_ready_is_programmer_misuse():
    proto = SimpleQueryProtocol()
    proto.send_startup(user="u")
    with pytest.raises(ValueError, match="only valid in READY"):
        proto.send_query("SELECT 1")


@pytest.mark.issue(256)
def test_send_query_while_busy_is_programmer_misuse():
    proto = _at_ready()
    proto.send_query("SELECT 1")
    with pytest.raises(ValueError, match="only valid in READY"):
        proto.send_query("SELECT 2")


@pytest.mark.issue(256)
def test_terminate_closes_engine_and_then_messages_desync():
    proto = _at_ready()
    assert proto.send_terminate() == _builder.build_terminate()
    assert proto.state is ProtocolState.CLOSED
    with pytest.raises(ProtocolError, match=r"ParameterStatus.*CLOSED"):
        proto.receive_bytes(_parameter_status("k", "v"))
