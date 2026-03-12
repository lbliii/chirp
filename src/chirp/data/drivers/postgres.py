"""PostgreSQL driver helpers for chirp.data."""

from chirp.data.errors import DriverNotInstalledError
from chirp.data.types import DatabaseConfig


async def create_pool(config: DatabaseConfig) -> object:
    """Create a PostgreSQL connection pool."""
    try:
        import asyncpg
    except ImportError:
        msg = (
            "chirp.data requires 'asyncpg' for PostgreSQL databases. "
            "Install it with: pip install chirp[data-pg]"
        )
        raise DriverNotInstalledError(msg) from None

    return await asyncpg.create_pool(
        config.url,
        min_size=1,
        max_size=config.pool_size,
    )
