"""Connection-level wire lifecycle regressions for pelt."""

from __future__ import annotations

from typing import cast

import pytest

from chirp.data.drivers._pelt import _transport
from chirp.data.drivers._pelt._protocol import (
    ExtendedQueryProtocol,
    PreparedStatementCache,
    ProtocolState,
    TransactionStatus,
)
from chirp.data.drivers._pelt.connection import Connection, Cursor, Record, _QueryResult
from chirp.data.drivers._pelt.errors import PostgresError
from chirp.data.drivers._pelt.types import ConnectionConfig


def _frame(tag: bytes, payload: bytes) -> bytes:
    return tag + (len(payload) + 4).to_bytes(4, "big") + payload


def _error_response(*fields: tuple[str, str]) -> bytes:
    payload = b"".join(code.encode() + value.encode() + b"\x00" for code, value in fields)
    return _frame(b"E", payload + b"\x00")


def _ready(status: bytes) -> bytes:
    return _frame(b"Z", status)


def _command_complete(tag: str) -> bytes:
    return _frame(b"C", tag.encode() + b"\x00")


def _row_description(name: str, type_oid: int) -> bytes:
    payload = (
        (1).to_bytes(2, "big")
        + name.encode()
        + b"\x00"
        + (0).to_bytes(4, "big")
        + (0).to_bytes(2, "big")
        + type_oid.to_bytes(4, "big")
        + (4).to_bytes(2, "big", signed=True)
        + (-1).to_bytes(4, "big", signed=True)
        + (0).to_bytes(2, "big")
    )
    return _frame(b"T", payload)


def _data_row(value: bytes) -> bytes:
    payload = (1).to_bytes(2, "big") + len(value).to_bytes(4, "big") + value
    return _frame(b"D", payload)


class _ScriptedStream:
    """Replay one backend network chunk per receive call."""

    def __init__(self, responses: list[bytes]) -> None:
        self.responses = list(responses)
        self.sent: list[bytes] = []
        self.extra_attributes = {}

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if not self.responses:
            return b""
        return self.responses.pop(0)[:max_bytes]

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def aclose(self) -> None:
        return None


class _BatchedConnection:
    def __init__(self, batches: list[list[Record]]) -> None:
        self.batches = list(batches)
        self.max_rows: list[int] = []

    async def _execute_portal(
        self, sql: str, params: tuple[object, ...], *, max_rows: int
    ) -> tuple[_QueryResult, bool]:
        del sql, params
        return self._next(max_rows)

    async def _resume_portal(self, *, max_rows: int) -> tuple[_QueryResult, bool]:
        return self._next(max_rows)

    def _next(self, max_rows: int) -> tuple[_QueryResult, bool]:
        self.max_rows.append(max_rows)
        rows = self.batches.pop(0)
        result = _QueryResult(rows=rows, command_tag=None)
        return result, bool(self.batches)


@pytest.mark.issue(260)
async def test_cursor_releases_consumed_batches() -> None:
    batches = [
        [Record(("n",), (0,)), Record(("n",), (1,))],
        [Record(("n",), (2,)), Record(("n",), (3,))],
        [Record(("n",), (4,))],
    ]
    conn = _BatchedConnection(batches)
    cursor = Cursor(cast(Connection, conn), "SELECT n", (), prefetch=2)

    seen: list[int] = []
    async for row in cursor:
        seen.append(row["n"])
        assert len(cursor._rows) <= 2

    assert seen == [0, 1, 2, 3, 4]
    assert conn.max_rows == [2, 2, 2]


@pytest.mark.issue(259)
async def test_error_drains_ready_frame_before_rollback_and_reuse() -> None:
    raw = _ScriptedStream(
        [
            _error_response(
                ("S", "ERROR"),
                ("V", "ERROR"),
                ("C", "22012"),
                ("M", "division by zero"),
            ),
            _ready(b"E"),
            _command_complete("ROLLBACK"),
            _ready(b"I"),
            _row_description("recovered", 23)
            + _data_row(b"1")
            + _command_complete("SELECT 1")
            + _ready(b"I"),
        ]
    )
    protocol = ExtendedQueryProtocol(
        state=ProtocolState.READY,
        transaction_status=TransactionStatus.IN_TRANSACTION,
        cache=PreparedStatementCache(),
    )
    conn = Connection(
        stream=_transport.PGStream(stream=raw),
        protocol=protocol,
        config=ConnectionConfig(),
    )

    with pytest.raises(PostgresError) as caught:
        await conn.execute("SELECT 1 / 0")

    assert caught.value.sqlstate == "22012"
    assert conn._protocol.transaction_status is TransactionStatus.IN_FAILED_TRANSACTION
    assert len(raw.responses) == 3

    await conn.reset_if_needed()
    assert conn._protocol.transaction_status is TransactionStatus.IDLE
    row = await conn.fetchrow("SELECT 1 AS recovered")
    assert dict(row) == {"recovered": 1}
    assert raw.responses == []
