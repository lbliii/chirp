"""Redis-backed rate limit backend. Requires redis package."""

from chirp.errors import ConfigurationError


class RedisRateLimitBackend:
    """Redis-backed sliding window rate limiter."""

    __slots__ = ("_prefix", "_redis_url")

    def __init__(self, redis_url: str, key_prefix: str = "chirp:ratelimit:") -> None:
        import importlib.util

        if importlib.util.find_spec("redis.asyncio") is None:
            raise ConfigurationError(
                "RedisRateLimitBackend requires 'redis'. Install with: pip install chirp[redis]"
            ) from None
        self._redis_url = redis_url
        self._prefix = key_prefix

    async def check_and_update(
        self,
        key: str,
        now: float,
        *,
        requests: int,
        window_seconds: int,
        block_seconds: int,
    ) -> tuple[bool, int]:
        import redis.asyncio as redis

        full_key = self._prefix + key
        block_key = full_key + ":block"
        client = redis.from_url(self._redis_url)
        try:
            # Check block first
            blocked = await client.get(block_key)
            if blocked:
                ttl = await client.ttl(block_key)
                if ttl > 0:
                    return False, max(1, ttl)

            # Sliding window: use sorted set, score = timestamp
            window_key = full_key + ":window"
            await client.zremrangebyscore(window_key, 0, now - window_seconds)
            count = await client.zcard(window_key)
            if count >= requests:
                await client.setex(block_key, block_seconds, "1")
                return False, block_seconds
            await client.zadd(window_key, {str(now): now})
            await client.expire(window_key, window_seconds)
            return True, 0
        finally:
            await client.aclose()
