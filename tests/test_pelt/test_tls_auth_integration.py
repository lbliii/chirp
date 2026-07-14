"""Issue #691 — live PostgreSQL TLS and authentication boundary."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from chirp.data.drivers._pelt import connection as pelt_connection
from chirp.data.drivers._pelt.errors import PostgresError, TLSError
from chirp.data.drivers._pelt.types import ConnectionConfig

PG_TLS_DSN = os.environ.get("CHIRP_TEST_PG_TLS_DSN")
PG_PASSWORD_DSN = os.environ.get("CHIRP_TEST_PG_PASSWORD_DSN")
PG_TLS_CA = os.environ.get("CHIRP_TEST_PG_TLS_CA")
PG_BAD_TLS_CA = os.environ.get("CHIRP_TEST_PG_BAD_TLS_CA")
requires_tls_pg = pytest.mark.skipif(
    not all((PG_TLS_DSN, PG_PASSWORD_DSN, PG_TLS_CA, PG_BAD_TLS_CA)),
    reason="live PostgreSQL TLS/auth fixture is not configured",
)


def _config(
    dsn: str,
    *,
    sslmode: str,
    host: str | None = None,
    rootcert: str | None = None,
    password: str | None = None,
) -> ConnectionConfig:
    config = ConnectionConfig.from_dsn(dsn)
    return replace(
        config,
        host=host or config.host,
        password=config.password if password is None else password,
        ssl=sslmode,
        sslrootcert=rootcert,
    )


async def _ssl_status(config: ConnectionConfig) -> bool:
    conn = await pelt_connection.Connection.connect(config)
    try:
        row = await conn.fetchrow("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
    finally:
        await conn.close()
    assert row is not None
    return bool(row["ssl"])


@requires_tls_pg
@pytest.mark.issue(691)
@pytest.mark.parametrize(
    ("sslmode", "host", "uses_ca", "expected_tls"),
    [
        ("verify-full", "localhost", True, True),
        ("verify-ca", "127.0.0.1", True, True),
        ("require", "localhost", False, True),
        ("prefer", "localhost", False, True),
        ("disable", "127.0.0.1", False, False),
    ],
)
async def test_live_sslmode_matrix(
    sslmode: str,
    host: str,
    uses_ca: bool,
    expected_tls: bool,
) -> None:
    assert PG_TLS_DSN is not None
    config = _config(
        PG_TLS_DSN,
        sslmode=sslmode,
        host=host,
        rootcert=PG_TLS_CA if uses_ca else None,
    )
    assert await _ssl_status(config) is expected_tls


@requires_tls_pg
@pytest.mark.issue(691)
@pytest.mark.parametrize(
    ("dsn_name", "expected_user"),
    [("scram", "chirp"), ("password", "pelt_password")],
)
async def test_live_scram_and_password_authentication(
    dsn_name: str,
    expected_user: str,
) -> None:
    dsn = PG_TLS_DSN if dsn_name == "scram" else PG_PASSWORD_DSN
    assert dsn is not None
    conn = await pelt_connection.Connection.connect(_config(dsn, sslmode="require"))
    try:
        row = await conn.fetchrow("SELECT current_user AS current_user")
    finally:
        await conn.close()
    assert row is not None
    assert row["current_user"] == expected_user


@requires_tls_pg
@pytest.mark.issue(691)
async def test_live_bad_credentials_are_actionable() -> None:
    assert PG_TLS_DSN is not None
    config = _config(PG_TLS_DSN, sslmode="require", password="wrong-password")

    with pytest.raises(PostgresError) as caught:
        await pelt_connection.Connection.connect(config)

    assert caught.value.sqlstate == "28P01"
    assert caught.value.code == "PELT_PG_28P01"
    assert caught.value.doc.endswith("#pelt_pg_sqlstate")


@requires_tls_pg
@pytest.mark.issue(691)
async def test_live_bad_ca_is_actionable() -> None:
    assert PG_TLS_DSN is not None
    config = _config(
        PG_TLS_DSN,
        sslmode="verify-ca",
        rootcert=PG_BAD_TLS_CA,
    )

    with pytest.raises(TLSError, match="TLS handshake failed") as caught:
        await pelt_connection.Connection.connect(config)

    assert caught.value.code == "PELT_TLS_FAILED"
    assert caught.value.hint is not None
    assert "sslrootcert" in caught.value.hint


@requires_tls_pg
@pytest.mark.issue(691)
async def test_live_bad_hostname_is_actionable() -> None:
    assert PG_TLS_DSN is not None
    config = _config(
        PG_TLS_DSN,
        sslmode="verify-full",
        host="127.0.0.1",
        rootcert=PG_TLS_CA,
    )

    with pytest.raises(TLSError, match="TLS handshake failed") as caught:
        await pelt_connection.Connection.connect(config)

    assert caught.value.code == "PELT_TLS_FAILED"
    assert caught.value.hint is not None
    assert "hostname" in caught.value.hint
