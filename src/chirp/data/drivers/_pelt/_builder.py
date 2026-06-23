"""Sans-I/O encoding: build PostgreSQL frontend (client → server) messages.

:class:`MessageBuilder` accumulates a message body as a ``list[bytes]`` and joins it once on
``getvalue`` — never ``+=`` on bytes in a loop (the patitas ``stringbuilder`` idiom). The
``build_*`` helpers wrap a body in the wire frame (1-byte tag + Int32 length). The startup
message is special-cased: it has no tag. This module touches no socket and no anyio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Frontend message tags, pre-interned as module constants (cf. pounce _fast_h1.py).
_TAG_QUERY = b"Q"
_TAG_PARSE = b"P"
_TAG_BIND = b"B"
_TAG_DESCRIBE = b"D"
_TAG_EXECUTE = b"E"
_TAG_SYNC = b"S"
_TAG_FLUSH = b"H"
_TAG_CLOSE = b"C"
_TAG_TERMINATE = b"X"
_TAG_PASSWORD = b"p"
_NUL = b"\x00"

# Protocol 3.0 (major 3, minor 0), used by the startup message.
PROTOCOL_VERSION = (3 << 16) | 0


class MessageBuilder:
    """Accumulates a frontend message body, joined once on :meth:`getvalue`."""

    __slots__ = ("_parts",)

    def __init__(self) -> None:
        self._parts: list[bytes] = []

    def write_bytes(self, data: bytes) -> None:
        if data:
            self._parts.append(data)

    def write_byte(self, value: int) -> None:
        self._parts.append(bytes((value,)))

    def write_int16(self, value: int) -> None:
        self._parts.append(value.to_bytes(2, "big", signed=True))

    def write_int32(self, value: int) -> None:
        self._parts.append(value.to_bytes(4, "big", signed=True))

    def write_cstring(self, text: str) -> None:
        self._parts.append(text.encode("utf-8"))
        self._parts.append(_NUL)

    def getvalue(self) -> bytes:
        return b"".join(self._parts)


def frame(tag: bytes, body: bytes) -> bytes:
    """Wrap ``body`` in a tagged wire frame: ``tag + Int32(len(body) + 4) + body``."""
    if len(tag) != 1:
        msg = f"message tag must be exactly one byte (got {tag!r})"
        raise ValueError(msg)
    return tag + (len(body) + 4).to_bytes(4, "big") + body


def build_startup(*, user: str, database: str = "", **params: str) -> bytes:
    """The untagged StartupMessage: protocol version + ``key\\0value\\0`` pairs + a final NUL."""
    b = MessageBuilder()
    b.write_int32(PROTOCOL_VERSION)
    b.write_cstring("user")
    b.write_cstring(user)
    if database:
        b.write_cstring("database")
        b.write_cstring(database)
    for key, value in params.items():
        b.write_cstring(key)
        b.write_cstring(value)
    b.write_byte(0)  # terminating empty key
    body = b.getvalue()
    return (len(body) + 4).to_bytes(4, "big") + body


def build_query(sql: str) -> bytes:
    """A simple-protocol ``Query`` (tag ``'Q'``)."""
    b = MessageBuilder()
    b.write_cstring(sql)
    return frame(_TAG_QUERY, b.getvalue())


def build_parse(*, name: str, query: str, param_oids: Sequence[int] = ()) -> bytes:
    """Extended-protocol ``Parse`` (tag ``'P'``). ``param_oids`` may be empty (server infers)."""
    b = MessageBuilder()
    b.write_cstring(name)
    b.write_cstring(query)
    b.write_int16(len(param_oids))
    for oid in param_oids:
        b.write_int32(oid)
    return frame(_TAG_PARSE, b.getvalue())


def build_bind(
    *,
    portal: str = "",
    statement: str = "",
    params: Sequence[bytes | None] = (),
) -> bytes:
    """Extended-protocol ``Bind`` (tag ``'B'``). Text-format params/results for the E1 spine;
    per-codec binary formats arrive in epic E2."""
    b = MessageBuilder()
    b.write_cstring(portal)
    b.write_cstring(statement)
    b.write_int16(0)  # zero format codes → all params use the default (text) format
    b.write_int16(len(params))
    for value in params:
        if value is None:
            b.write_int32(-1)
        else:
            b.write_int32(len(value))
            b.write_bytes(value)
    b.write_int16(0)  # zero result format codes → all results in text format
    return frame(_TAG_BIND, b.getvalue())


def build_describe(*, kind: str, name: str = "") -> bytes:
    """Extended-protocol ``Describe`` (tag ``'D'``). ``kind`` is ``'S'`` (statement) or
    ``'P'`` (portal)."""
    if kind not in ("S", "P"):
        msg = f"describe kind must be 'S' or 'P' (got {kind!r})"
        raise ValueError(msg)
    b = MessageBuilder()
    b.write_byte(ord(kind))
    b.write_cstring(name)
    return frame(_TAG_DESCRIBE, b.getvalue())


def build_execute(*, portal: str = "", max_rows: int = 0) -> bytes:
    """Extended-protocol ``Execute`` (tag ``'E'``). ``max_rows == 0`` means "all rows"."""
    b = MessageBuilder()
    b.write_cstring(portal)
    b.write_int32(max_rows)
    return frame(_TAG_EXECUTE, b.getvalue())


def build_sync() -> bytes:
    """Extended-protocol ``Sync`` (tag ``'S'``)."""
    return frame(_TAG_SYNC, b"")


def build_flush() -> bytes:
    """``Flush`` (tag ``'H'``)."""
    return frame(_TAG_FLUSH, b"")


def build_close(*, kind: str, name: str = "") -> bytes:
    """Extended-protocol ``Close`` (tag ``'C'``). ``kind`` is ``'S'`` (statement) or
    ``'P'`` (portal)."""
    if kind not in ("S", "P"):
        msg = f"close kind must be 'S' or 'P' (got {kind!r})"
        raise ValueError(msg)
    b = MessageBuilder()
    b.write_byte(ord(kind))
    b.write_cstring(name)
    return frame(_TAG_CLOSE, b.getvalue())


def build_terminate() -> bytes:
    """``Terminate`` (tag ``'X'``) — a graceful goodbye."""
    return frame(_TAG_TERMINATE, b"")


def build_password(password: bytes) -> bytes:
    """A cleartext/MD5 ``PasswordMessage`` (tag ``'p'``)."""
    return frame(_TAG_PASSWORD, password + _NUL)


def build_sasl_initial(*, mechanism: str, initial_response: bytes) -> bytes:
    """SASL initial ``PasswordMessage``: mechanism cstring + Int32 length + payload."""
    b = MessageBuilder()
    b.write_cstring(mechanism)
    b.write_int32(len(initial_response))
    b.write_bytes(initial_response)
    return frame(_TAG_PASSWORD, b.getvalue())


def build_sasl_continue(response: bytes) -> bytes:
    """SASL continuation ``PasswordMessage``: raw mechanism response bytes only."""
    return frame(_TAG_PASSWORD, response)


__all__ = [
    "PROTOCOL_VERSION",
    "MessageBuilder",
    "build_bind",
    "build_close",
    "build_describe",
    "build_execute",
    "build_flush",
    "build_parse",
    "build_password",
    "build_query",
    "build_sasl_continue",
    "build_sasl_initial",
    "build_startup",
    "build_sync",
    "build_terminate",
    "frame",
]
