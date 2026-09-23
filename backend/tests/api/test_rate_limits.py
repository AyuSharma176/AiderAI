import pytest

from app.services.rate_limit import (
    RateLimitBackendError,
    RateLimiter,
    RateLimitExceeded,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def ttl(self, key: str) -> int:
        return 42

    async def eval(self, _script: str, _numkeys: int, key: str, seconds: int) -> int:
        count = await self.incr(key)
        if count == 1:
            await self.expire(key, seconds)
        return count


class UnavailableRedis:
    async def eval(self, *args) -> int:
        raise ConnectionError("redis password=secret")

    async def ttl(self, key: str) -> int:
        return -1


@pytest.mark.asyncio
async def test_separate_scope_counter_returns_retry_after() -> None:
    limiter = RateLimiter(FakeRedis(), window_seconds=60)
    await limiter.check("auth", "client-a", limit=1)

    with pytest.raises(RateLimitExceeded) as caught:
        await limiter.check("auth", "client-a", limit=1)

    assert caught.value.retry_after == 42
    await limiter.check("chat", "client-a", limit=1)


@pytest.mark.asyncio
async def test_redis_outage_maps_to_safe_backend_error() -> None:
    limiter = RateLimiter(UnavailableRedis(), window_seconds=60)

    with pytest.raises(RateLimitBackendError, match="temporarily unavailable"):
        await limiter.check("upload", "client-a", limit=1)
