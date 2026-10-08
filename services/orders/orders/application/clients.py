from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException
from service_common.circuit_breaker import CircuitBreaker, CircuitOpenError, breaker_for
from service_common.logging import correlation_id_var

from orders.infrastructure.config import settings


class ContextApiClient:
    def __init__(self, base_url: str, breaker: CircuitBreaker | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.breaker = breaker or breaker_for(
            self.base_url,
            settings.circuit_breaker_failure_threshold,
            settings.circuit_breaker_reset_seconds,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        headers = {"X-Correlation-ID": correlation_id_var.get()}
        if access_token is not None:
            headers["Authorization"] = f"Bearer {access_token}"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        def send_request() -> httpx.Response:
            with httpx.Client(timeout=settings.downstream_timeout_seconds) as client:
                response = client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json_body,
                    headers=headers,
                )
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    "Downstream returned a transient failure.",
                    request=response.request,
                    response=response,
                )
            return response

        try:
            response = self.breaker.call(send_request)
        except CircuitOpenError as exc:
            raise HTTPException(
                status_code=503,
                detail="A required service is temporarily unavailable.",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail="A required service is temporarily unavailable.",
            ) from exc
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Requested resource was not found.")
        if response.status_code == 409:
            try:
                message = (
                    response.json()
                    .get("error", {})
                    .get("message", "Request conflicts with current state.")
                )
            except ValueError:
                message = "Request conflicts with current state."
            raise HTTPException(status_code=409, detail=message)
        if response.status_code >= 500:
            raise HTTPException(
                status_code=503, detail="A required service is temporarily unavailable."
            )
        if response.is_error:
            raise HTTPException(status_code=502, detail="A required service rejected the request.")
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502, detail="A required service returned invalid data."
            ) from exc


class CatalogClient(ContextApiClient):
    def __init__(self) -> None:
        super().__init__(settings.catalog_base_url)

    def get_product(self, product_id: UUID) -> dict[str, Any]:
        return self.request("GET", f"/v1/products/{product_id}")


class InventoryClient(ContextApiClient):
    def __init__(self) -> None:
        super().__init__(settings.inventory_base_url)

    def reserve(self, order_id: UUID, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/inventory/reservations",
            json_body={"orderId": str(order_id), "items": items},
            idempotency_key=f"reserve-{order_id}",
        )

    def commit(self, reservation_id: UUID) -> dict[str, Any]:
        return self.request("POST", f"/v1/inventory/reservations/{reservation_id}/commit")

    def release(self, reservation_id: UUID) -> dict[str, Any]:
        return self.request("POST", f"/v1/inventory/reservations/{reservation_id}/release")


class PaymentClient(ContextApiClient):
    def __init__(self) -> None:
        super().__init__(settings.payments_base_url)

    def create(
        self, order_id: UUID, payment_method_token: str, access_token: str
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/payments",
            json_body={"orderId": str(order_id), "paymentMethodToken": payment_method_token},
            idempotency_key=f"payment-{order_id}",
            access_token=access_token,
        )
