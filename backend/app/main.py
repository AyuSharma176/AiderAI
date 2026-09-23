from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="SupportAI API", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(conversations_router)
    application.include_router(chat_router)
    application.include_router(documents_router)

    @application.exception_handler(401)
    async def unauthorized_handler(_request, exc):
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict) and detail.get("code") == "invalid_token":
            return JSONResponse(status_code=401, content=detail)
        return JSONResponse(
            status_code=401,
            content={"code": "unauthorized", "message": "Authentication required"},
        )
    return application


app = create_app()
