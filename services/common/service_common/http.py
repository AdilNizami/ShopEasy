from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from contextvars import Token

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from service_common.logging import correlation_id_var

logger = logging.getLogger("shop_easy.http")


def error_body(request: Request, code: str, message: str, retryable: bool) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlationId": getattr(request.state, "correlation_id", correlation_id_var.get()),
            "retryable": retryable,
        }
    }


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        supplied_id = request.headers.get("X-Correlation-ID", "")
        try:
            correlation_id = str(uuid.UUID(supplied_id)) if supplied_id else str(uuid.uuid4())
        except ValueError:
            correlation_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id
        token: Token[str] = correlation_id_var.set(correlation_id)
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed method=%s path=%s",
                request.method,
                request.url.path,
            )
            raise
        else:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "request completed method=%s path=%s status_code=%d duration_ms=%.2f",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("request validation failed")
        return JSONResponse(
            status_code=422,
            content=error_body(request, "VALIDATION_ERROR", "Request validation failed.", False),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_by_status = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
            504: "UPSTREAM_TIMEOUT",
        }
        code = code_by_status.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                request,
                code,
                str(exc.detail),
                exc.status_code in {429, 502, 503, 504},
            ),
            headers=exc.headers,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # SQLAlchemy exception text can include bound values; keep credentials
        # and other sensitive parameters out of service logs.
        logger.error("database operation failed")
        return JSONResponse(
            status_code=503,
            content=error_body(request, "SERVICE_UNAVAILABLE", "Database is unavailable.", True),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled service error")
        return JSONResponse(
            status_code=500,
            content=error_body(request, "INTERNAL_ERROR", "An unexpected error occurred.", False),
        )


def install_health_routes(app: FastAPI, service_name: str, sessions: sessionmaker[Session]) -> None:
    @app.get("/health/live", tags=["Health"], include_in_schema=False)
    async def liveness() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    @app.get("/health/ready", tags=["Health"], include_in_schema=False, response_model=None)
    async def readiness(request: Request) -> dict[str, str] | JSONResponse:
        try:
            with sessions() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("readiness database check failed")
            return JSONResponse(
                status_code=503,
                content=error_body(
                    request, "SERVICE_UNAVAILABLE", "Database is unavailable.", True
                ),
            )
        return {"status": "ok", "service": service_name}
