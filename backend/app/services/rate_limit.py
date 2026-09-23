from functools import lru_cache
from typing import Annotated, Protocol

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.config import Settings, get_settings


class RedisCounter(Protocol):
    async def incr(self, key: str) -> int: ...
    async def expire(self, key: str, seconds: int) -> bool: ...
    async def ttl(self, key: str) -> int: ...


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after


class RateLimitBackendError(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, redis: RedisCounter, *, window_seconds: int) -> None:
        self.redis = redis
        self.window_seconds = window_seconds

    async def check(self, scope: str, identity: str, *, limit: int) -> None:
        key = f"rate:{scope}:{identity}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window_seconds)
            if count > limit:
                retry_after = await self.redis.ttl(key)
                raise RateLimitExceeded(max(1, retry_after))
        except RateLimitExceeded:
            raise
        except Exception as exc:
            raise RateLimitBackendError(
                "Rate limiting is temporarily unavailable"
            ) from exc


@lru_cache
def get_redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _identity(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", maxsplit=1)[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


async def _check(
    request: Request, redis: RedisCounter, settings: Settings, scope: str, limit: int
) -> None:
    if settings.app_env == "test":
        return
    await RateLimiter(redis, window_seconds=settings.rate_limit_window_seconds).check(
        scope, _identity(request), limit=limit
    )


async def enforce_auth_rate_limit(
    request: Request,
    redis: Annotated[RedisCounter, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    await _check(request, redis, settings, "auth", settings.auth_rate_limit)


async def enforce_chat_rate_limit(
    request: Request,
    redis: Annotated[RedisCounter, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    await _check(request, redis, settings, "chat", settings.chat_rate_limit)


async def enforce_upload_rate_limit(
    request: Request,
    redis: Annotated[RedisCounter, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    await _check(request, redis, settings, "upload", settings.upload_rate_limit)
