"""SQLite driver helpers for chirp.data."""

from chirp.data.errors import DataError
from chirp.data.types import DatabaseConfig


def parse_sqlite_path(url: str) -> str:
    """Extract the file path from a sqlite:// URL."""
    # sqlite:///path/to/db  ->  /path/to/db
    # sqlite:///:memory:    ->  :memory:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        return url[len(prefix) :]
    prefix_short = "sqlite://"
    if url.startswith(prefix_short):
        return url[len(prefix_short) :]
    msg = f"Invalid SQLite URL: {url!r}"
    raise DataError(msg)


async def create_pool(config: DatabaseConfig) -> object:
    """Create a SQLite connection (pool is the single connection)."""
    import sqlite3

    from chirp.data._sqlite import connect as sqlite_connect

    path = parse_sqlite_path(config.url)
    conn = await sqlite_connect(path)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent read performance
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn  # SQLite: pool IS the connection
