from fastapi import APIRouter


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
async def readiness() -> dict[str, str]:
    return {"status": "ready"}

