"""Issue #954: server-cursor batches keep wire ownership while decoding in parallel."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from chirp.data.drivers._pelt import _codecs, _runtime, _transport
from chirp.data.drivers._pelt import connection as _connection
from chirp.data.drivers._pelt._messages import FieldDescription, RowDescription
from chirp.data.drivers._pelt._protocol import (
    ExtendedQueryProtocol,
    PreparedStatementCache,
    ProtocolState,
    TransactionStatus,
)
from chirp.data.drivers._pelt.connection import Connection
from chirp.data.drivers._pelt.types import ConnectionConfig

pytestmark = pytest.mark.issue(954)


def _frame(tag: bytes, payload: bytes = b"") -> bytes:
    return tag + (len(payload) + 4).to_bytes(4, "big") + payload


def _ready() -> bytes:
    return _frame(b"Z", b"I")


def _row_description(column_count: int = 1) -> bytes:
    fields = b"".join(
        f"n{index}".encode()
        + b"\x00"
        + (0).to_bytes(4, "big")
        + (0).to_bytes(2, "big")
        + _codecs.OID_INT4.to_bytes(4, "big")
        + (4).to_bytes(2, "big", signed=True)
        + (-1).to_bytes(4, "big", signed=True)
        + (0).to_bytes(2, "big")
        for index in range(column_count)
    )
    payload = column_count.to_bytes(2, "big") + fields
    return _frame(b"T", payload)


def _data_row(value: int, column_count: int = 1) -> bytes:
    encoded = value.to_bytes(4, "big", signed=True)
    payload = (
        column_count.to_bytes(2, "big") + (len(encoded).to_bytes(4, "big") + encoded) * column_count
    )
    return _frame(b"D", payload)


class _ThreadRecordingStream:
    """Replay backend exchanges and record which thread owns every wire call."""

    def __init__(self, responses: list[bytes]) -> None:
        self.responses = list(responses)
        self.thread_ids: list[int] = []
        self.extra_attributes: dict[str, Any] = {}

    async def receive(self, max_bytes: int = 65536) -> bytes:
        del max_bytes
        self.thread_ids.append(threading.get_native_id())
        return self.responses.pop(0) if self.responses else b""

    async def send(self, data: bytes) -> None:
        del data
        self.thread_ids.append(threading.get_native_id())

    async def aclose(self) -> None:
        return None


@pytest.mark.skipif(
    not _runtime.is_free_threading_enabled(),
    reason="requires a free-threaded build with GIL disabled",
)
async def test_cursor_keeps_wire_serial_while_each_batch_decodes_on_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_size = 65
    row_count = 130
    column_count = 4
    first = b"".join(_data_row(value, column_count) for value in range(batch_size))
    second = b"".join(_data_row(value, column_count) for value in range(batch_size, row_count))
    raw_stream = _ThreadRecordingStream(
        [
            _frame(b"1") + _frame(b"t", b"\x00\x00") + _row_description(column_count) + _ready(),
            _frame(b"2") + first + _frame(b"s") + _ready(),
            second + _frame(b"C", b"SELECT 130\x00") + _ready(),
        ]
    )
    protocol = ExtendedQueryProtocol(
        state=ProtocolState.READY,
        transaction_status=TransactionStatus.IDLE,
        cache=PreparedStatementCache(),
    )
    conn = Connection(
        stream=_transport.PGStream(stream=raw_stream),
        protocol=protocol,
        config=ConnectionConfig(),
    )
    decoder_threads: set[int] = set()
    decoder_threads_lock = threading.Lock()

    def decode(value: bytes | None) -> int | None:
        with decoder_threads_lock:
            decoder_threads.add(threading.get_native_id())
        # Keep each chunk alive long enough to make worker overlap deterministic.
        time.sleep(0.005)
        return None if value is None else int.from_bytes(value, "big", signed=True)

    monkeypatch.setattr(
        _codecs,
        "build_codec_plan",
        lambda description, registry: (decode,) * len(description.fields),
    )

    owner_thread = threading.get_native_id()
    rows = [row["n0"] async for row in conn.cursor("SELECT n", prefetch=batch_size)]

    assert rows == list(range(row_count))
    assert protocol.state is ProtocolState.READY
    assert raw_stream.thread_ids
    assert set(raw_stream.thread_ids) == {owner_thread}
    assert owner_thread not in decoder_threads
    assert len(decoder_threads) >= 2


def test_cursor_decode_policy_falls_back_to_owner_thread_with_gil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    description = RowDescription(
        fields=tuple(
            FieldDescription(
                name=f"n{index}",
                table_oid=0,
                column_attr=0,
                type_oid=_codecs.OID_INT4,
                type_size=4,
                type_modifier=-1,
                format_code=1,
            )
            for index in range(4)
        )
    )
    plan = _codecs.build_codec_plan(description, _codecs.build_default_registry().snapshot())
    pending = [tuple(value.to_bytes(4, "big", signed=True) for _ in plan) for value in range(100)]
    decoder_threads: set[int] = set()
    original_decode = _connection._decode_row_values

    def record_decode(codec_plan, raw_values):
        decoder_threads.add(threading.get_native_id())
        return original_decode(codec_plan, raw_values)

    monkeypatch.setattr(_runtime, "is_free_threading_enabled", lambda: False)
    monkeypatch.setattr(_connection, "_decode_row_values", record_decode)

    owner_thread = threading.get_native_id()
    rows = _connection._decode_rows(
        plan, tuple(field.name for field in description.fields), pending
    )

    assert [row[0] for row in rows] == list(range(100))
    assert decoder_threads == {owner_thread}


async def test_cursor_decode_failure_joins_workers_and_leaves_protocol_reusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row_count = 65
    raw_stream = _ThreadRecordingStream(
        [
            _frame(b"1") + _frame(b"t", b"\x00\x00") + _row_description() + _ready(),
            _frame(b"2")
            + b"".join(_data_row(value) for value in range(row_count))
            + _frame(b"C", b"SELECT 65\x00")
            + _ready(),
            _row_description()
            + _frame(b"D", b"\x00\x01\x00\x00\x00\x019")
            + _frame(b"C", b"SELECT 1\x00")
            + _ready(),
        ]
    )
    protocol = ExtendedQueryProtocol(
        state=ProtocolState.READY,
        transaction_status=TransactionStatus.IDLE,
        cache=PreparedStatementCache(),
    )
    conn = Connection(
        stream=_transport.PGStream(stream=raw_stream),
        protocol=protocol,
        config=ConnectionConfig(),
    )
    active_decoders = 0
    active_lock = threading.Lock()

    def decode(value: bytes | None) -> int | None:
        nonlocal active_decoders
        with active_lock:
            active_decoders += 1
        try:
            if value == (7).to_bytes(4, "big", signed=True):
                raise ValueError("bad row")
            time.sleep(0.001)
            if value is None:
                return None
            return int.from_bytes(value, "big", signed=True) if len(value) == 4 else int(value)
        finally:
            with active_lock:
                active_decoders -= 1

    monkeypatch.setattr(_runtime, "should_parallelize", lambda *, n_rows, n_cols: True)
    monkeypatch.setattr(
        _codecs,
        "build_codec_plan",
        lambda description, registry: (decode,) * len(description.fields),
    )

    with pytest.raises(ValueError, match="bad row"):
        await anext(conn.cursor("SELECT n", prefetch=row_count))

    assert active_decoders == 0
    assert protocol.state is ProtocolState.READY
    recovered = await conn.fetchrow("SELECT 9 AS n")
    assert recovered is not None
    assert recovered["n0"] == 9
