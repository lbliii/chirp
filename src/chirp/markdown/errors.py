"""Markdown layer error hierarchy."""

from chirp.errors import ChirpError


class MarkdownError(ChirpError):
    """Base for all chirp.markdown errors."""


class MarkdownNotInstalledError(MarkdownError):
    """Raised when patitas is not installed."""
