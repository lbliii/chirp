"""anyio connection surface for pelt (epic E5).

Mirrors the asyncpg-shaped API the ``Database`` facade calls: ``fetch`` / ``fetchrow`` /
``execute`` / ``executemany`` / ``cursor`` / ``transaction``, plus LISTEN/NOTIFY helpers.
Owns the I/O loop that drives :class:`~._protocol.ExtendedQueryProtocol` against a
:class:`~._transport.PGStream`.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

import anyio
from anyio import EndOfStream

from chirp.data.drivers._pelt import _builder, _codecs, _params, _transport
from chirp.data.drivers._pelt._protocol import (
    CommandCompleteEvent,
    DataRowEvent,
    ErrorEvent,
    ExtendedQueryProtocol,
    NotificationEvent,
    ParameterDescriptionEvent,
    PortalSuspendedEvent,
    PreparedStatementCache,
    ProtocolState,
    ReadyEvent,
    RowDescriptionEvent,
    SimpleQueryProtocol,
    TransactionStatus,
)
from chirp.data.drivers._pelt.errors import PeltConnectionError, ProtocolError
from chirp.data.drivers._pelt.types import ConnectionConfig

_IdentRe = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Record(Mapping[str, Any]):
    """Dict-able row mapping (``dict(row)`` for the facade)."""

    __slots__ = ("_keys", "_values")

    def __init__(self, keys: Sequence[str], values: Sequence[Any]) -> None:
        self._keys = tuple(keys)
        self._values = tuple(values)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        idx = self._keys.index(key)
        return self._values[idx]

    def __iter__(self):
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self):
        return self._keys

    def values(self):
        return self._values

    def items(self):
        return zip(self._keys, self._values, strict=True)


@dataclass(slots=True)
class _QueryResult:
    rows: list[Record]
    command_tag: str | None


class Transaction(AbstractAsyncContextManager["Transaction"]):
    """asyncpg-shaped transaction handle."""

    __slots__ = ("_conn", "_started")

    def __init__(self, conn: Connection) -> None:
        self._conn = conn
        self._started = False

    async def start(self) -> None:
        if not self._started:
            await self._conn.execute("BEGIN")
            self._started = True

    async def commit(self) -> None:
        if self._started:
            await self._conn.execute("COMMIT")
            self._started = False

    async def rollback(self) -> None:
        if self._started:
            await self._conn.execute("ROLLBACK")
            self._started = False

    async def __aenter__(self) -> Transaction:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc is not None:
            await self.rollback()
        else:
            await self.commit()


class Cursor:
    """Server-side cursor over an open portal (``prefetch`` batch size)."""

    __slots__ = ("_conn", "_done", "_idx", "_prefetch", "_rows", "_sql", "_params")

    def __init__(
        self,
        conn: Connection,
        sql: str,
        params: tuple[Any, ...],
        *,
        prefetch: int,
    ) -> None:
        self._conn = conn
        self._sql = sql
        self._params = params
        self._prefetch = prefetch
        self._rows: list[Record] = []
        self._done = False
        self._idx = 0

    def __aiter__(self) -> Cursor:
        return self

    async def __anext__(self) -> Record:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        if self._done:
            raise StopAsyncIteration
        await self._fetch_more(first=not self._rows)
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return row

    async def _fetch_more(self, *, first: bool) -> None:
        if first:
            result, suspended = await self._conn._execute_portal(
                self._sql,
                self._params,
                max_rows=self._prefetch,
            )
            self._rows.extend(result.rows)
            self._done = not suspended
            return
        result, suspended = await self._conn._resume_portal(max_rows=self._prefetch)
        self._rows.extend(result.rows)
        self._done = not suspended


class Connection:
    """One authenticated PostgreSQL session."""

    __slots__ = (
        "_active_row_description",
        "_closed",
        "_config",
        "_listener_tg",
        "_listener_tg_cm",
        "_listeners",
        "_protocol",
        "_stream",
    )

    def __init__(
        self,
        *,
        stream: _transport.PGStream,
        protocol: ExtendedQueryProtocol,
        config: ConnectionConfig,
    ) -> None:
        self._stream = stream
        self._protocol = protocol
        self._config = config
        self._closed = False
        self._active_row_description = None
        self._listeners: dict[str, list[Callable[[Connection, int, str, str], None]]] = {}
        self._listener_tg: anyio.abc.TaskGroup | None = None
        self._listener_tg_cm: Any = None

    @classmethod
    async def connect(
        cls,
        config: ConnectionConfig,
        *,
        statement_cache_size: int = 100,
    ) -> Connection:
        """Open, authenticate, and return a ready connection."""
        session = await _transport.connect_session(config)
        protocol = ExtendedQueryProtocol(
            state=ProtocolState.READY,
            transaction_status=session.protocol.transaction_status,
            cache=PreparedStatementCache(size=statement_cache_size),
        )
        return cls(stream=session.stream, protocol=protocol, config=config)

    def transaction(self) -> Transaction:
        return Transaction(self)

    def cursor(self, sql: str, /, *params: Any, prefetch: int = 100) -> Cursor:
        return Cursor(self, sql, params, prefetch=prefetch)

    async def fetch(self, sql: str, /, *params: Any) -> list[Record]:
        result = await self._execute(sql, params)
        return result.rows

    async def fetchrow(self, sql: str, /, *params: Any) -> Record | None:
        rows = await self.fetch(sql, *params)
        return rows[0] if rows else None

    async def execute(self, sql: str, /, *params: Any) -> str:
        result = await self._execute(sql, params)
        return result.command_tag or "OK"

    async def executemany(self, sql: str, params_seq: Sequence[tuple[Any, ...]], /) -> None:
        for params in params_seq:
            await self.execute(sql, *params)

    async def prepare(self, sql: str) -> None:
        """Warm the statement cache (asyncpg compatibility)."""
        await self._ensure_prepared(sql, ())

    async def add_listener(
        self, channel: str, callback: Callable[[Connection, int, str, str], None]
    ) -> None:
        listeners = self._listeners.setdefault(channel, [])
        if callback in listeners:
            return
        listeners.append(callback)
        if len(listeners) == 1:
            await self.execute(f"LISTEN {_quote_ident(channel)}")
            await self._ensure_listen_reader()

    async def remove_listener(
        self, channel: str, callback: Callable[[Connection, int, str, str], None]
    ) -> None:
        listeners = self._listeners.get(channel)
        if not listeners or callback not in listeners:
            return
        listeners.remove(callback)
        if not listeners:
            del self._listeners[channel]
            await self.execute(f"UNLISTEN {_quote_ident(channel)}")
        if not self._listeners and self._listener_tg is not None:
            await self._stop_listen_reader()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._stop_listen_reader()
        if self._protocol.state is not ProtocolState.CLOSED:
            await self._stream.send(self._protocol.send_terminate())
        await self._stream.stream.aclose()

    async def reset_if_needed(self) -> None:
        """Rollback an open or failed transaction before returning to the pool."""
        status = self._protocol.transaction_status
        if status in (TransactionStatus.IN_TRANSACTION, TransactionStatus.IN_FAILED_TRANSACTION):
            await self.execute("ROLLBACK")

    async def _execute(self, sql: str, params: tuple[Any, ...]) -> _QueryResult:
        if not params:
            return await self._execute_simple(sql)
        result, _ = await self._execute_portal(sql, params, max_rows=0)
        return result

    async def _execute_simple(self, sql: str) -> _QueryResult:
        simple = SimpleQueryProtocol(
            state=ProtocolState.READY,
            transaction_status=self._protocol.transaction_status,
        )
        outbound = simple.send_query(sql)
        events = await self._roundtrip(outbound, protocol=simple)
        if simple.transaction_status is not None:
            self._protocol.transaction_status = simple.transaction_status
        result, _ = self._collect_query_result(events)
        return result

    async def _execute_portal(
        self,
        sql: str,
        params: tuple[Any, ...],
        *,
        max_rows: int,
    ) -> tuple[_QueryResult, bool]:
        statement = await self._ensure_prepared(sql, ())
        wire_params = tuple(_params.encode_param(p) for p in params)
        outbound = self._protocol.send_bind_execute(
            statement=statement.name,
            params=wire_params,
            max_rows=max_rows,
        )
        if statement.row_description is not None:
            self._protocol.seed_row_description(statement.row_description)
            self._active_row_description = statement.row_description
        events = await self._roundtrip(outbound)
        return self._collect_query_result(events)

    async def _resume_portal(self, *, max_rows: int) -> tuple[_QueryResult, bool]:
        if self._active_row_description is not None:
            self._protocol.seed_row_description(self._active_row_description)
        outbound = self._protocol.resume_execute(max_rows=max_rows)
        events = await self._roundtrip(outbound)
        return self._collect_query_result(events)

    async def _ensure_prepared(self, sql: str, param_oids: Sequence[int]) -> Any:
        statement, outbound = self._protocol.prepare(sql, param_oids)
        if outbound is None:
            return statement
        events = await self._roundtrip(outbound)
        for event in events:
            if isinstance(event, ParameterDescriptionEvent):
                self._protocol.record_parameter_description(sql, param_oids, event.type_oids)
            elif isinstance(event, RowDescriptionEvent):
                self._protocol.record_row_description(sql, param_oids, event.description)
        return self._protocol.cache.get(sql, param_oids) or statement

    async def _roundtrip(
        self,
        outbound: bytes,
        *,
        protocol: ExtendedQueryProtocol | SimpleQueryProtocol | None = None,
    ) -> list[Any]:
        engine = protocol if protocol is not None else self._protocol
        if isinstance(engine, ExtendedQueryProtocol):
            await self._flush_pending_closes()
        await self._stream.send(outbound)
        events: list[Any] = []
        ready = False
        while not ready:
            new = engine.receive_bytes(b"")
            if new:
                self._dispatch_sideband(new)
                events.extend(new)
                if any(isinstance(e, ReadyEvent) for e in new):
                    ready = True
                    continue
            try:
                chunk = await self._stream.stream.receive(65536)
            except EndOfStream:
                chunk = b""
            if not chunk:
                if engine.state is ProtocolState.READY:
                    break
                msg = "connection closed by server"
                raise PeltConnectionError(msg)
            new = engine.receive_bytes(chunk)
            self._dispatch_sideband(new)
            for event in new:
                if isinstance(event, ErrorEvent):
                    raise event.error
            events.extend(new)
            if any(isinstance(e, ReadyEvent) for e in new):
                ready = True
        if protocol is None and isinstance(engine, ExtendedQueryProtocol):
            self._protocol.state = engine.state
            self._protocol.transaction_status = engine.transaction_status
        return events

    async def _flush_pending_closes(self) -> None:
        for stmt in self._protocol.drain_pending_close():
            await self._stream.send(_builder.build_close(kind="S", name=stmt.name))

    def _dispatch_sideband(self, events: Sequence[Any]) -> None:
        for event in events:
            if isinstance(event, NotificationEvent):
                for callback in self._listeners.get(event.channel, ()):
                    callback(self, event.pid, event.channel, event.payload)

    def _collect_query_result(self, events: Sequence[Any]) -> tuple[_QueryResult, bool]:
        rows: list[Record] = []
        command_tag: str | None = None
        suspended = False
        codec_plan: tuple[Any, ...] | None = None
        column_names: tuple[str, ...] = ()
        registry = _codecs.DEFAULT_REGISTRY.snapshot()

        for event in events:
            if isinstance(event, RowDescriptionEvent):
                column_names = tuple(field.name for field in event.description.fields)
                codec_plan = _codecs.build_codec_plan(event.description, registry)
            elif isinstance(event, DataRowEvent):
                if codec_plan is None:
                    column_names = tuple(field.name for field in event.description.fields)
                    codec_plan = _codecs.build_codec_plan(event.description, registry)
                values = tuple(
                    decoder(raw)
                    for decoder, raw in zip(codec_plan, event.row.values, strict=True)
                )
                rows.append(Record(column_names, values))
            elif isinstance(event, CommandCompleteEvent):
                command_tag = event.tag
            elif isinstance(event, PortalSuspendedEvent):
                suspended = True
        return _QueryResult(rows=rows, command_tag=command_tag), suspended

    async def _ensure_listen_reader(self) -> None:
        if self._listener_tg is not None:
            return
        self._listener_tg_cm = anyio.create_task_group()
        await self._listener_tg_cm.__aenter__()
        self._listener_tg = self._listener_tg_cm
        self._listener_tg.start_soon(self._listen_forever)

    async def _stop_listen_reader(self) -> None:
        if self._listener_tg_cm is None:
            return
        await self._listener_tg_cm.__aexit__(None, None, None)
        self._listener_tg = None
        self._listener_tg_cm = None

    async def _listen_forever(self) -> None:
        while not self._closed:
            try:
                chunk = await self._stream.stream.receive(65536)
            except EndOfStream:
                break
            if not chunk:
                break
            events = self._protocol.receive_bytes(chunk)
            self._dispatch_sideband(events)


def _quote_ident(name: str) -> str:
    if _IdentRe.fullmatch(name):
        return name
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


__all__ = [
    "Connection",
    "Cursor",
    "Record",
    "Transaction",
]
