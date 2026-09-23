import re
from contextvars import ContextVar
from time import monotonic
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_context: ContextVar[str] = ContextVar("request_id", default="unknown")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def get_request_id() -> str:
    return request_id_context.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid4())
        token = request_id_context.set(request_id)
        request.state.request_id = request_id
        started = monotonic()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            structlog.get_logger().info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=int((monotonic() - started) * 1000),
            )
            return response
        except Exception:
            structlog.get_logger().exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                latency_ms=int((monotonic() - started) * 1000),
            )
            raise
        finally:
            request_id_context.reset(token)
