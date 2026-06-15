"""Sans-I/O framing: raw backend bytes → typed :data:`PGMessage` objects.

The single entry point is :func:`parse_message`, which reads one length-prefixed backend
message from the front of a buffer and reports how many bytes it consumed. ``None`` means
"need more data" — the caller carries the leftover bytes forward and tries again after the
next read (cf. pounce ``_fast_h1.py`` / ``sync_protocol.py``). This module touches **no
socket and no anyio**, so it is fuzzable in isolation and parallelizable across free-threaded
workers.

Robustness contract (proven by the E1 fuzz test): on *any* input, :func:`parse_message`
either returns ``(message, consumed)``, returns ``(None, 0)`` for an incomplete buffer, or
raises :class:`ProtocolError`. It never raises anything else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    FieldDescription,
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
from chirp.data.drivers._pelt.errors import ProtocolError

if TYPE_CHECKING:
    from collections.abc import Callable

    from chirp.data.drivers._pelt._messages import PGMessage

# Header = 1-byte tag + Int32 length. The length counts itself but not the tag byte.
_HEADER_SIZE = 5
_NUL = 0

# Authentication sub-type codes (the Int32 that follows tag 'R').
_AUTH_OK = 0
_AUTH_CLEARTEXT = 3
_AUTH_MD5 = 5
_AUTH_SASL = 10
_AUTH_SASL_CONTINUE = 11
_AUTH_SASL_FINAL = 12
_MD5_SALT_LEN = 4


class _Reader:
    """A bounded cursor over a single message payload. Every accessor raises
    :class:`ProtocolError` on underflow, so parsers never see a raw ``IndexError``."""

    __slots__ = ("_buf", "_pos")

    def __init__(self, buf: memoryview) -> None:
        self._buf = buf
        self._pos = 0

    def _need(self, n: int) -> None:
        if n < 0 or self._pos + n > len(self._buf):
            msg = f"truncated message payload: wanted {n} byte(s) at offset {self._pos}"
            raise ProtocolError(msg)

    def read_byte(self) -> int:
        self._need(1)
        value = self._buf[self._pos]
        self._pos += 1
        return value

    def read_int16(self) -> int:
        self._need(2)
        value = int.from_bytes(self._buf[self._pos : self._pos + 2], "big", signed=True)
        self._pos += 2
        return value

    def read_int32(self) -> int:
        self._need(4)
        value = int.from_bytes(self._buf[self._pos : self._pos + 4], "big", signed=True)
        self._pos += 4
        return value

    def read_bytes(self, n: int) -> bytes:
        self._need(n)
        value = bytes(self._buf[self._pos : self._pos + n])
        self._pos += n
        return value

    def read_cstring(self) -> str:
        end = self._pos
        limit = len(self._buf)
        while end < limit and self._buf[end] != _NUL:
            end += 1
        if end >= limit:
            msg = f"unterminated C-string at offset {self._pos}"
            raise ProtocolError(msg)
        raw = bytes(self._buf[self._pos : end])
        self._pos = end + 1  # skip the NUL terminator
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = f"invalid UTF-8 in C-string at offset {self._pos}: {exc}"
            raise ProtocolError(msg) from exc

    def read_rest(self) -> bytes:
        value = bytes(self._buf[self._pos :])
        self._pos = len(self._buf)
        return value


def _parse_authentication(r: _Reader) -> PGMessage:
    subtype = r.read_int32()
    if subtype == _AUTH_OK:
        return AuthenticationOk()
    if subtype == _AUTH_CLEARTEXT:
        return AuthenticationCleartextPassword()
    if subtype == _AUTH_MD5:
        return AuthenticationMD5Password(salt=r.read_bytes(_MD5_SALT_LEN))
    if subtype == _AUTH_SASL:
        mechanisms: list[str] = []
        while True:
            name = r.read_cstring()
            if not name:
                break
            mechanisms.append(name)
        return AuthenticationSASL(mechanisms=tuple(mechanisms))
    if subtype == _AUTH_SASL_CONTINUE:
        return AuthenticationSASLContinue(data=r.read_rest())
    if subtype == _AUTH_SASL_FINAL:
        return AuthenticationSASLFinal(data=r.read_rest())
    msg = f"unsupported authentication request sub-type {subtype}"
    raise ProtocolError(msg)


def _parse_parameter_status(r: _Reader) -> PGMessage:
    return ParameterStatus(name=r.read_cstring(), value=r.read_cstring())


def _parse_backend_key_data(r: _Reader) -> PGMessage:
    return BackendKeyData(pid=r.read_int32(), secret_key=r.read_int32())


def _parse_ready_for_query(r: _Reader) -> PGMessage:
    return ReadyForQuery(status=chr(r.read_byte()))


def _read_field(r: _Reader) -> FieldDescription:
    # Field members are read in wire order; keyword arguments evaluate left-to-right, so the
    # cursor advances correctly. Kept as a helper so the parser stays a clean comprehension.
    return FieldDescription(
        name=r.read_cstring(),
        table_oid=r.read_int32(),
        column_attr=r.read_int16(),
        type_oid=r.read_int32(),
        type_size=r.read_int16(),
        type_modifier=r.read_int32(),
        format_code=r.read_int16(),
    )


def _parse_row_description(r: _Reader) -> PGMessage:
    count = r.read_int16()
    return RowDescription(fields=tuple(_read_field(r) for _ in range(count)))


def _parse_data_row(r: _Reader) -> PGMessage:
    count = r.read_int16()
    values: list[bytes | None] = []
    for _ in range(count):
        size = r.read_int32()
        values.append(None if size == -1 else r.read_bytes(size))
    return DataRow(values=tuple(values))


def _parse_command_complete(r: _Reader) -> PGMessage:
    return CommandComplete(tag=r.read_cstring())


def _read_fields(r: _Reader) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = []
    while True:
        code = r.read_byte()
        if code == _NUL:
            break
        fields.append((chr(code), r.read_cstring()))
    return tuple(fields)


def _parse_error_response(r: _Reader) -> PGMessage:
    return ErrorResponse(fields=_read_fields(r))


def _parse_notice_response(r: _Reader) -> PGMessage:
    return NoticeResponse(fields=_read_fields(r))


def _parse_notification(r: _Reader) -> PGMessage:
    return NotificationResponse(
        pid=r.read_int32(), channel=r.read_cstring(), payload=r.read_cstring()
    )


def _parse_parameter_description(r: _Reader) -> PGMessage:
    count = r.read_int16()
    return ParameterDescription(type_oids=tuple(r.read_int32() for _ in range(count)))


def _parse_parse_complete(_r: _Reader) -> PGMessage:
    return ParseComplete()


def _parse_bind_complete(_r: _Reader) -> PGMessage:
    return BindComplete()


def _parse_close_complete(_r: _Reader) -> PGMessage:
    return CloseComplete()


def _parse_no_data(_r: _Reader) -> PGMessage:
    return NoData()


def _parse_portal_suspended(_r: _Reader) -> PGMessage:
    return PortalSuspended()


def _parse_empty_query(_r: _Reader) -> PGMessage:
    return EmptyQueryResponse()


# Dispatch table: backend tag byte → payload parser. Built once at import.
_PARSERS: dict[int, Callable[[_Reader], PGMessage]] = {
    ord("R"): _parse_authentication,
    ord("S"): _parse_parameter_status,
    ord("K"): _parse_backend_key_data,
    ord("Z"): _parse_ready_for_query,
    ord("T"): _parse_row_description,
    ord("D"): _parse_data_row,
    ord("C"): _parse_command_complete,
    ord("E"): _parse_error_response,
    ord("N"): _parse_notice_response,
    ord("A"): _parse_notification,
    ord("t"): _parse_parameter_description,
    ord("1"): _parse_parse_complete,
    ord("2"): _parse_bind_complete,
    ord("3"): _parse_close_complete,
    ord("n"): _parse_no_data,
    ord("s"): _parse_portal_suspended,
    ord("I"): _parse_empty_query,
}


def _tag_repr(tag: int) -> str:
    char = chr(tag)
    return repr(char) if char.isprintable() else f"0x{tag:02x}"


def parse_message(buf: bytes | memoryview) -> tuple[PGMessage | None, int]:
    """Parse one backend message from the front of ``buf``.

    Returns ``(message, consumed)`` where ``consumed`` is the number of bytes the message
    occupied, or ``(None, 0)`` when ``buf`` does not yet hold a complete message. Raises
    :class:`ProtocolError` on a malformed header, an unknown tag, or a truncated/garbled
    payload.
    """
    available = len(buf)
    if available < _HEADER_SIZE:
        return None, 0

    tag = buf[0]
    length = int.from_bytes(buf[1:_HEADER_SIZE], "big")
    if length < 4:
        msg = f"invalid message length {length} for tag {_tag_repr(tag)}"
        raise ProtocolError(msg)

    total = length + 1  # length excludes the tag byte
    if available < total:
        return None, 0

    parser = _PARSERS.get(tag)
    if parser is None:
        msg = f"unknown backend message tag {_tag_repr(tag)}"
        raise ProtocolError(msg)

    payload = memoryview(buf)[_HEADER_SIZE:total]
    try:
        message = parser(_Reader(payload))
    except ProtocolError:
        raise
    except (ValueError, IndexError, UnicodeDecodeError) as exc:
        msg = f"malformed payload for tag {_tag_repr(tag)}: {exc}"
        raise ProtocolError(msg) from exc
    return message, total
