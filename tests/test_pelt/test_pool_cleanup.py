"""Pool construction cleanup for partial PostgreSQL connection failures."""

from __future__ import annotations

import pytest

from chirp.data.drivers._pelt import pool as pelt_pool
from chirp.data.drivers._pelt.types import ConnectionConfig, PoolConfig


class _StubConnection:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.issue(691)
async def test_create_pool_closes_opened_connections_after_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[_StubConnection] = []

    class _FailingConnectionFactory:
        @classmethod
        async def connect(
            cls,
            config: ConnectionConfig,
            *,
            statement_cache_size: int,
            type_catalog: object | None = None,
        ) -> _StubConnection:
            del cls, config, statement_cache_size, type_catalog
            if opened:
                raise RuntimeError("second connection failed")
            conn = _StubConnection()
            opened.append(conn)
            return conn

    monkeypatch.setattr(pelt_pool, "Connection", _FailingConnectionFactory)

    with pytest.raises(RuntimeError, match="second connection failed"):
        await pelt_pool.create_pool(
            PoolConfig(connection=ConnectionConfig(), min_size=0, max_size=2)
        )

    assert len(opened) == 1
    assert opened[0].closed is True
