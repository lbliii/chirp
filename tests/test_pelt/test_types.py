"""E1.3 (#266) — PoolConfig / ConnectionConfig: DSN parsing, validation, immutability."""

from dataclasses import FrozenInstanceError

import pytest

from chirp.data.drivers._pelt.types import ConnectionConfig, PoolConfig


@pytest.mark.issue(266)
def test_from_dsn_parses_all_components():
    cfg = ConnectionConfig.from_dsn(
        "postgresql://alice:s3cr3t@db.example.com:6543/shop"
        "?sslmode=verify-full&sslrootcert=%2Fetc%2Fssl%2Fcerts%2Fchirp-ca.crt"
    )
    assert cfg.host == "db.example.com"
    assert cfg.port == 6543
    assert cfg.database == "shop"
    assert cfg.user == "alice"
    assert cfg.password == "s3cr3t"
    assert cfg.ssl == "verify-full"
    assert cfg.sslrootcert == "/etc/ssl/certs/chirp-ca.crt"


@pytest.mark.issue(266)
def test_from_dsn_applies_defaults():
    cfg = ConnectionConfig.from_dsn("postgres://localhost/mydb")
    assert cfg.port == 5432
    assert cfg.user == ""
    assert cfg.ssl == "prefer"
    assert cfg.database == "mydb"


@pytest.mark.issue(266)
def test_from_dsn_percent_decodes_credentials():
    cfg = ConnectionConfig.from_dsn("postgresql://u%40corp:p%3Aword@h/db")
    assert cfg.user == "u@corp"
    assert cfg.password == "p:word"


@pytest.mark.issue(266)
def test_from_dsn_rejects_non_postgres_scheme():
    with pytest.raises(ValueError, match="scheme"):
        ConnectionConfig.from_dsn("mysql://localhost/db")


@pytest.mark.issue(266)
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"port": 0}, "port"),
        ({"port": 70000}, "port"),
        ({"ssl": "bogus"}, "ssl"),
        ({"connect_timeout": 0}, "connect_timeout"),
    ],
)
def test_connection_config_validation(kwargs, match):
    with pytest.raises(ValueError, match=match):
        ConnectionConfig(**kwargs)


@pytest.mark.issue(266)
def test_connection_config_is_frozen():
    cfg = ConnectionConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.port = 1


@pytest.mark.issue(266)
def test_pool_config_from_dsn():
    pool = PoolConfig.from_dsn("postgresql://localhost/db", max_size=20)
    assert pool.max_size == 20
    assert pool.connection.database == "db"


@pytest.mark.issue(266)
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"max_size": 0}, "max_size"),
        ({"min_size": 5, "max_size": 2}, "max_size"),
        ({"min_size": -1}, "min_size"),
        ({"statement_cache_size": -1}, "statement_cache_size"),
    ],
)
def test_pool_config_validation(kwargs, match):
    with pytest.raises(ValueError, match=match):
        PoolConfig(connection=ConnectionConfig(), **kwargs)
