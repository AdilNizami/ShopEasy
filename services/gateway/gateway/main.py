from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncio
import json
import logging
import time

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from jwt import InvalidTokenError
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from gateway.settings import settings
from service_common.http import (
    CorrelationIdMiddleware,
    install_error_handlers,
)
from service_common.identity import Principal, TokenConfigurationError, decode_access_token
from service_common.logging import configure_logging, correlation_id_var

configure_logging(settings.log_level)
logger = logging.getLogger("shop_easy.gateway.observability")
ROUTES: tuple[tuple[str, str], ...] = (
    ("/v1/auth", "auth"),
    ("/v1/products", "catalog"),
    ("/v1/categories", "catalog"),
    ("/v1/carts", "orders"),
    ("/v1/checkout", "orders"),
    ("/v1/orders", "orders"),
    ("/v1/payments", "payments"),
    ("/v1/inventory/availability", "inventory"),
)
FORWARDED_REQUEST_HEADERS = {
    "accept",
    "authorization",
    "content-type",
    "idempotency-key",
    "if-match",
    "if-none-match",
}
FORWARDED_RESPONSE_HEADERS = {
    "cache-control",
    "content-type",
    "etag",
    "location",
    "retry-after",
    "www-authenticate",
}


def _is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _is_public_request(method: str, path: str) -> bool:
    if method == "POST" and path in {"/v1/auth/register", "/v1/auth/login"}:
        return True
    return method == "GET" and any(
        _is_under(path, prefix)
        for prefix in (
            "/v1/products",
            "/v1/categories",
            "/v1/inventory/availability",
        )
    )


def _decode_bearer(request: Request) -> Principal:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="A valid access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(token)
    except TokenConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _validate_bearer(request: Request) -> None:
    _decode_bearer(request)


def _validate_operator(request: Request) -> Principal:
    principal = _decode_bearer(request)
    if principal.role != "operator":
        raise HTTPException(status_code=403, detail="Operator access is required.")
    return principal


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    timeout = httpx.Timeout(
        settings.upstream_timeout_seconds,
        connect=settings.connect_timeout_seconds,
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.upstream_client = client
        yield


app = FastAPI(title="ShopEasy API Gateway", version="1.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.frontend_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)
install_error_handlers(app)


@app.get("/health/live", tags=["Health"], include_in_schema=False)
async def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


public_api = APIRouter()


@public_api.get("/internal/observability/services", include_in_schema=False)
async def service_health(request: Request) -> dict[str, object]:
    _validate_operator(request)
    client: httpx.AsyncClient = request.app.state.upstream_client

    async def check(name: str, url: str) -> dict[str, object]:
        started = time.perf_counter()
        try:
            response = await client.get(f"{url.rstrip('/')}/health/ready")
            elapsed = round((time.perf_counter() - started) * 1000)
            return {
                "name": name,
                "status": "healthy" if response.is_success else "unhealthy",
                "latencyMs": elapsed,
            }
        except httpx.HTTPError:
            return {"name": name, "status": "unhealthy", "latencyMs": None}

    results = await asyncio.gather(
        *(check(name, url) for name, url in settings.service_urls.items())
    )
    try:
        broker_response = await client.get(
            f"{settings.rabbitmq_management_url.rstrip('/')}/api/overview",
            auth=(settings.rabbitmq_user, settings.rabbitmq_password),
        )
        broker_status = "healthy" if broker_response.is_success else "unhealthy"
        broker_latency = round(broker_response.elapsed.total_seconds() * 1000)
    except httpx.HTTPError:
        broker_status = "unhealthy"
        broker_latency = None
    results.append({"name": "rabbitmq", "status": broker_status, "latencyMs": broker_latency})
    results.append({"name": "gateway", "status": "healthy", "latencyMs": 0})
    return {"items": results}


@public_api.get("/internal/observability/service/{service_name}", include_in_schema=False)
async def service_observability(service_name: str, request: Request) -> Response:
    _validate_operator(request)
    if service_name not in {"orders", "payments", "notifications"}:
        raise HTTPException(status_code=404, detail="Observability data is not available for this service.")
    url = f"{settings.service_urls[service_name].rstrip('/')}/internal/observability"
    try:
        upstream = await request.app.state.upstream_client.get(
            url,
            headers={
                "Authorization": request.headers.get("Authorization", ""),
                "X-Correlation-ID": correlation_id_var.get(),
            },
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Observability source timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Observability source is unavailable.") from exc
    return Response(content=upstream.content, status_code=upstream.status_code, media_type="application/json")


@public_api.get("/internal/observability/dlq", include_in_schema=False)
async def dead_letter_messages(request: Request) -> dict[str, object]:
    _validate_operator(request)
    client: httpx.AsyncClient = request.app.state.upstream_client
    queues = ("orders.events.v1.dlq", "notifications.events.v1.dlq")
    results: list[dict[str, object]] = []
    base = settings.rabbitmq_management_url.rstrip("/")
    auth = (settings.rabbitmq_user, settings.rabbitmq_password)
    for queue_name in queues:
        queue_path = f"{base}/api/queues/%2F/{queue_name}"
        try:
            queue_response = await client.get(queue_path, auth=auth)
            if queue_response.status_code == 404:
                results.append({"queue": queue_name, "count": 0, "items": [], "status": "available"})
                continue
            queue_response.raise_for_status()
            ready = int(queue_response.json().get("messages_ready", 0))
            items_response = await client.post(
                f"{queue_path}/get",
                auth=auth,
                json={"count": 10, "ackmode": "ack_requeue_true", "encoding": "auto", "truncate": 30000},
            )
            items_response.raise_for_status()
            messages = []
            for message in items_response.json():
                properties = message.get("properties") or {}
                headers = properties.get("headers") or {}
                try:
                    event = json.loads(message.get("payload") or "{}")
                except (TypeError, json.JSONDecodeError):
                    event = {}
                messages.append({
                    "queue": queue_name,
                    "eventId": event.get("eventId") or headers.get("x-event-id") or properties.get("message_id"),
                    "eventType": event.get("eventType"),
                    "producer": event.get("producer"),
                    "occurredAt": event.get("occurredAt"),
                    "correlationId": event.get("correlationId") or headers.get("x-correlation-id"),
                    "retryCount": headers.get("x-shop-easy-retry-count", 0),
                    "failureCategory": headers.get("x-failure-category"),
                    "failedAt": headers.get("x-failed-at"),
                })
            results.append({"queue": queue_name, "count": ready, "items": messages, "status": "available"})
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            results.append({"queue": queue_name, "count": None, "items": [], "status": "unavailable"})
            logger.warning("Could not read DLQ telemetry queue=%s error=%s", queue_name, type(exc).__name__)
    return {"queues": results}


@public_api.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy(full_path: str, request: Request) -> Response:
    path = f"/v1/{full_path}"
    target_service = next(
        (service for prefix, service in ROUTES if _is_under(path, prefix)),
        None,
    )
    if target_service is None:
        raise HTTPException(status_code=404, detail="API route not found.")

    requires_authentication = not _is_public_request(request.method, path)
    if requires_authentication:
        _validate_bearer(request)

    base_url = settings.service_urls[target_service].rstrip("/")
    url = f"{base_url}{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in FORWARDED_REQUEST_HEADERS
    }
    if not requires_authentication:
        headers.pop("authorization", None)
    headers["X-Correlation-ID"] = correlation_id_var.get()
    body = await request.body()

    try:
        upstream = await request.app.state.upstream_client.request(
            request.method,
            url,
            headers=headers,
            content=body if body else None,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="The requested service did not respond before the gateway timeout.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="The requested service is temporarily unavailable.",
        ) from exc

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in FORWARDED_RESPONSE_HEADERS
    }
    response_headers["X-Correlation-ID"] = correlation_id_var.get()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


app.include_router(public_api, prefix="/v1")
