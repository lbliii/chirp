"""E1.5 (#268) — parse_message: known messages, partial buffers, and fuzz robustness."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt import _messages as msgs
from chirp.data.drivers._pelt._framing import parse_message
from chirp.data.drivers._pelt.errors import ProtocolError


def _backend(tag: bytes, payload: bytes) -> bytes:
    """Frame a backend message the way Postgres would: tag + Int32 length + payload."""
    return tag + (len(payload) + 4).to_bytes(4, "big") + payload


@pytest.mark.issue(268)
def test_parse_ready_for_query():
    message, consumed = parse_message(_backend(b"Z", b"I"))
    assert isinstance(message, msgs.ReadyForQuery)
    assert message.status == "I"
    assert consumed == 6


@pytest.mark.issue(268)
def test_parse_parameter_status():
    message, _ = parse_message(_backend(b"S", b"server_version\x0017.0\x00"))
    assert isinstance(message, msgs.ParameterStatus)
    assert message.name == "server_version"
    assert message.value == "17.0"


@pytest.mark.issue(268)
def test_parse_error_response():
    payload = b"SERROR\x00C42P01\x00Mno such table\x00\x00"
    message, _ = parse_message(_backend(b"E", payload))
    assert isinstance(message, msgs.ErrorResponse)
    assert message.sqlstate == "42P01"
    assert message.message_text == "no such table"


@pytest.mark.issue(268)
def test_parse_row_description_and_data_row():
    field = (
        b"id\x00"
        + (0).to_bytes(4, "big")  # table OID
        + (0).to_bytes(2, "big")  # column attr
        + (23).to_bytes(4, "big")  # type OID (int4)
        + (4).to_bytes(2, "big")  # type size
        + (-1).to_bytes(4, "big", signed=True)  # type modifier
        + (0).to_bytes(2, "big")  # format code
    )
    rd, _ = parse_message(_backend(b"T", (1).to_bytes(2, "big") + field))
    assert isinstance(rd, msgs.RowDescription)
    assert rd.fields[0].name == "id"
    assert rd.fields[0].type_oid == 23

    dr_payload = (
        (2).to_bytes(2, "big")  # two columns
        + (2).to_bytes(4, "big")
        + b"42"  # first value
        + (-1).to_bytes(4, "big", signed=True)  # second value = NULL
    )
    dr, _ = parse_message(_backend(b"D", dr_payload))
    assert isinstance(dr, msgs.DataRow)
    assert dr.values == (b"42", None)


@pytest.mark.issue(268)
def test_incomplete_buffer_returns_none():
    full = _backend(b"Z", b"I")
    assert parse_message(full[:3]) == (None, 0)  # header not complete
    assert parse_message(full[:5]) == (None, 0)  # header complete, payload missing


@pytest.mark.issue(268)
def test_multiple_messages_framed_sequentially():
    stream = _backend(b"1", b"") + _backend(b"Z", b"I")
    first, c1 = parse_message(stream)
    assert isinstance(first, msgs.ParseComplete)
    second, c2 = parse_message(stream[c1:])
    assert isinstance(second, msgs.ReadyForQuery)
    assert c1 + c2 == len(stream)


@pytest.mark.issue(268)
def test_unknown_tag_raises():
    with pytest.raises(ProtocolError, match="unknown backend message tag"):
        parse_message(_backend(b"\xff", b""))


@pytest.mark.issue(268)
def test_invalid_length_raises():
    bad = b"Z" + (2).to_bytes(4, "big") + b"I"  # length 2 is below the 4-byte minimum
    with pytest.raises(ProtocolError, match="invalid message length"):
        parse_message(bad)


@pytest.mark.issue(268)
@given(data=st.binary(max_size=600))
def test_parse_message_never_crashes_on_arbitrary_bytes(data):
    # The framer's robustness contract: on ANY input, return (msg, n) / (None, 0),
    # or raise ProtocolError — never anything else.
    try:
        message, consumed = parse_message(data)
    except ProtocolError:
        return
    if message is None:
        assert consumed == 0
    else:
        assert 0 < consumed <= len(data)
