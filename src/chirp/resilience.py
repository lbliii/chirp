"""Resilience patterns for external dependencies.

Documents recommended patterns for timeouts, retries, and circuit breakers
when calling external services. Chirp does not bundle a circuit breaker;
use ``tenacity`` or similar for retries with backoff.

HTTP client (use AppConfig.http_timeout, http_retries)::

    import httpx

    async with httpx.AsyncClient(
        timeout=app.config.http_timeout,
    ) as client:
        response = await client.get(url)

For retries with backoff, use tenacity::

    from tenacity import retry, stop_after_attempt, wait_exponential

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetch_with_retry(url: str) -> str:
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text

Database: ``Database`` uses ``connect_timeout`` and ``connect_retries``
from its config. Pass them when constructing::

    db = Database(
        "postgresql://...",
        connect_timeout=10.0,
        connect_retries=3,
    )
"""
