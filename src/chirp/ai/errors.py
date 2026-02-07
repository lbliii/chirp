"""AI layer error hierarchy."""

from chirp.errors import ChirpError


class AIError(ChirpError):
    """Base for all chirp.ai errors."""


class ProviderNotInstalledError(AIError):
    """Raised when httpx is not installed."""


class ProviderError(AIError):
    """Raised when an LLM provider returns an error."""

    def __init__(self, provider: str, status: int, detail: str) -> None:
        self.provider = provider
        self.status = status
        self.detail = detail
        super().__init__(f"{provider} returned {status}: {detail}")


class StructuredOutputError(AIError):
    """Raised when structured output cannot be parsed into the target type."""
