"""Data layer error hierarchy."""

from chirp.errors import ChirpError


class DataError(ChirpError):
    """Base for all chirp.data errors."""


class DriverNotInstalledError(DataError):
    """Raised when the required database driver is not installed."""


class ConnectionError(DataError):
    """Raised when a database connection cannot be established."""


class QueryError(DataError):
    """Raised when a SQL query fails."""


class MigrationError(DataError):
    """Raised when a migration fails or is invalid."""
