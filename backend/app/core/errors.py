"""Application error hierarchy and the single JSON error envelope.

Services raise these; handlers turn them into ``{"error": {code, message, details}}``.
Unexpected exceptions become a generic 500 so internals never leak to clients.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class ErpTimeout(AppError):
    """The ERP did not answer in time. The request may or may not have been applied."""

    status_code = 504
    code = "erp_timeout"


def _envelope(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(_envelope(exc.code, exc.message, exc.details), exc.status_code)


_HTTP_CODES = {
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_failed",
}


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    """Framework errors (unknown route, wrong method) use the same envelope as ours."""
    assert isinstance(exc, HTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return JSONResponse(_envelope(code, str(exc.detail), {}), exc.status_code)


async def _handle_request_validation(_: Request, exc: Exception) -> JSONResponse:
    """Malformed requests (bad body, missing header) get the envelope, without echoing input."""
    assert isinstance(exc, RequestValidationError)
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(
        _envelope(ValidationFailed.code, "Request validation failed", {"errors": errors}),
        ValidationFailed.status_code,
    )


async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", exc_info=exc)
    return JSONResponse(_envelope("internal_error", "Internal server error", {}), 500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(HTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(Exception, _handle_unexpected)
