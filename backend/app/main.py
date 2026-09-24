from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.orders import router as orders_router
from app.core.config import get_settings
from app.core.errors import error_response, safe_http_error
from app.core.logging import configure_logging
from app.middleware.body_limit import UploadBodyLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.services.rate_limit import RateLimitBackendError, RateLimitExceeded


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    application = FastAPI(title="AiderAI API", version="0.1.0")
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(UploadBodyLimitMiddleware, max_bytes=settings.max_upload_bytes)
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
    application.include_router(integrations_router)
    application.include_router(orders_router)

    @application.exception_handler(HTTPException)
    async def http_error_handler(_request, exc: HTTPException):
        code, message = safe_http_error(exc.detail, exc.status_code)
        return error_response(exc.status_code, code, message, headers=exc.headers)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request, _exc: RequestValidationError):
        return error_response(422, "validation_error", "Request validation failed")

    @application.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_request, exc: RateLimitExceeded):
        return error_response(
            429,
            "rate_limit_exceeded",
            "Too many requests",
            headers={"Retry-After": str(exc.retry_after)},
        )

    @application.exception_handler(RateLimitBackendError)
    async def rate_limit_backend_handler(_request, _exc: RateLimitBackendError):
        return error_response(
            503,
            "rate_limit_unavailable",
            "Request protection is temporarily unavailable",
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request, _exc: Exception):
        return error_response(500, "internal_error", "An unexpected error occurred")

    return application


app = create_app()
