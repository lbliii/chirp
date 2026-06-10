"""Data layer error hierarchy."""

from chirp.errors import ChirpError


class DataError(ChirpError):
    """Base for all chirp.data errors."""


class DriverNotInstalledError(DataError):
    """Raised when the required database driver is not installed."""


class DatabaseConnectionError(DataError):
    """Raised when a database connection cannot be established."""


class QueryError(DataError):
    """Raised when a SQL query fails."""


class MigrationError(DataError):
    """Raised when a migration fails or is invalid."""


class ShapeError(DataError):
    """Raised when a ``@shape`` target is invalid or a Shape SQL cannot be bound.

    Fired by ``@shape`` on a non-dataclass / non-frozen / non-slots target, by
    the registry on a same-name collision with a different class, and by
    ``Shape.fetch`` when a declared ``:name`` placeholder has no bound value.
    """
