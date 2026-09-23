from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.database import get_engine
from app.services.rate_limit import get_redis_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


def get_readiness_checker() -> Callable[[], Awaitable[dict[str, bool]]]:
    return probe_readiness


@router.get("/ready")
async def readiness(
    checker: Annotated[
        Callable[[], Awaitable[dict[str, bool]]], Depends(get_readiness_checker)
    ],
):
    dependencies = await checker()
    if not all(dependencies.values()):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "dependencies": dependencies},
        )
    return {"status": "ready", "dependencies": dependencies}


async def probe_readiness() -> dict[str, bool]:
    database_ready = False
    redis_ready = False
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        database_ready = True
    except Exception:  # noqa: BLE001 - readiness returns booleans, never internals
        database_ready = False
    try:
        redis_ready = bool(await get_redis_client().ping())
    except Exception:  # noqa: BLE001 - readiness returns booleans, never internals
        redis_ready = False
    return {"database": database_ready, "redis": redis_ready}
