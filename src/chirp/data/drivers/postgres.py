"""PostgreSQL driver helpers for chirp.data."""

from chirp.data.types import DatabaseConfig


async def create_pool(config: DatabaseConfig) -> object:
    """Create a PostgreSQL connection pool via the in-tree pelt driver."""
    from chirp.data.drivers import _pelt

    pool_config = _pelt.PoolConfig.from_dsn(
        config.url,
        min_size=1,
        max_size=max(1, config.pool_size),
    )
    return await _pelt.create_pool(pool_config)
