from typing import Any

from fastapi.responses import JSONResponse

from app.middleware.request_context import get_request_id


def error_payload(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "request_id": get_request_id()}


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(code, message),
        headers=headers,
    )


def safe_http_error(detail: Any, status_code: int) -> tuple[str, str]:
    if isinstance(detail, dict):
        code = str(detail.get("code", "request_failed"))
        message = str(detail.get("message", "Request failed"))
        return code, message
    defaults = {
        401: ("unauthorized", "Authentication required"),
        403: ("forbidden", "Access denied"),
        404: ("not_found", "Resource not found"),
    }
    return defaults.get(status_code, ("request_failed", "Request failed"))
