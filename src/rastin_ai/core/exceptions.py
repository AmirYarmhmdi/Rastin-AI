"""File guide.

- Use: Defines application exceptions and FastAPI error handlers.
- Usage: Import AppException, app_exception_handler, register_exception_handlers,
  and 1 more from rastin_ai.core.exceptions.
- Duties: Defines AppException, app_exception_handler, register_exception_handlers,
  and unexpected_exception_handler and related helper logic.
- Depends on: External packages only: fastapi, fastapi.responses, logging, and
  typing.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# This is the base error type for expected application errors.
class AppException(Exception):
    """Base exception for application-level errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "APPLICATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        super().__init__(message)


# This builds the common API error response shape.
def _error_payload(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }


# This turns AppException errors into clean JSON responses.
async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    # Log the error code and path, but do not expose secrets.
    logger.warning(
        "Application exception at %s: %s",
        request.url.path,
        exc.error_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


# This catches unexpected errors at the API boundary.
async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    # Log the full traceback internally for debugging.
    logger.exception("Unexpected exception at %s", request.url.path)
    # Return a safe message so clients do not see internal details.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_payload(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal error occurred.",
        ),
    )


# This connects the custom error handlers to the FastAPI app.
def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers for the FastAPI app."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
