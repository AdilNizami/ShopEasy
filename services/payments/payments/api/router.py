from __future__ import annotations

import hashlib
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from service_common.circuit_breaker import CircuitOpenError, breaker_for
from service_common.events import event_record_fields, new_event
from service_common.identity import Principal, get_current_principal
from service_common.logging import correlation_id_var
from service_common.schemas import ErrorResponse
from sqlalchemy.orm import Session

from payments.api.schemas import MoneyResponse, PaymentRequest, PaymentResponse
from payments.domain.mock_provider import MockPaymentProvider
from payments.infrastructure.config import settings
from payments.infrastructure.database import SessionLocal
from payments.infrastructure.models import OutboxEventRecord, PaymentRecord, PaymentRequestRecord

router = APIRouter(prefix="/payments", tags=["Payments"])
provider = MockPaymentProvider()


def get_session():
    with SessionLocal() as session:
        yield session


def _fingerprint(payload: PaymentRequest) -> str:
    source = f"{payload.order_id}:{payload.payment_method_token}"
    return hashlib.sha256(source.encode()).hexdigest()


def _response(payment: PaymentRecord) -> PaymentResponse:
    return PaymentResponse(
        id=payment.id,
        order_id=payment.order_id,
        status=payment.status,
        amount=MoneyResponse(amount=payment.amount, currency=payment.currency),
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


def _order_for_user(order_id: UUID, access_token: str) -> dict:
    base_url = settings.orders_base_url.rstrip("/")
    url = f"{base_url}/v1/orders/{order_id}"

    def fetch_order() -> httpx.Response:
        with httpx.Client(timeout=settings.downstream_timeout_seconds) as client:
            response = client.get(
                url,
                headers={
                    "X-Correlation-ID": correlation_id_var.get(),
                    "Authorization": f"Bearer {access_token}",
                },
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise httpx.HTTPStatusError(
                "Orders returned a transient failure.", request=response.request, response=response
            )
        return response

    try:
        response = breaker_for(
            base_url,
            settings.circuit_breaker_failure_threshold,
            settings.circuit_breaker_reset_seconds,
        ).call(fetch_order)
    except CircuitOpenError as exc:
        raise HTTPException(status_code=503, detail="Orders service is unavailable.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Orders service is unavailable.") from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Order not found.")
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="A valid access token is required.")
    if response.is_error:
        raise HTTPException(status_code=503, detail="Orders service is unavailable.")

    try:
        order = response.json()
        if not isinstance(order, dict):
            raise ValueError("Invalid order response.")
        return order
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Orders returned an invalid response.") from exc


def _order_total(order_id: UUID, access_token: str) -> tuple[Decimal, str]:
    order = _order_for_user(order_id, access_token)
    try:
        if order["status"] != "PENDING_PAYMENT":
            raise HTTPException(status_code=409, detail="Order is not awaiting payment.")
        amount = Decimal(order["total"]["amount"])
        currency = str(order["total"]["currency"])
        if amount < 0 or len(currency) != 3:
            raise ValueError("Invalid order total.")
        return amount, currency
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Orders returned an invalid response.") from exc


def _authorize_order_access(order_id: UUID, access_token: str) -> None:
    _order_for_user(order_id, access_token)


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    responses={503: {"model": ErrorResponse, "description": "Orders service is unavailable."}},
)
def create_payment(
    payload: PaymentRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> PaymentResponse:
    fingerprint = _fingerprint(payload)
    request_record = session.get(PaymentRequestRecord, idempotency_key)
    if request_record is not None:
        if request_record.fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key was reused.")
        payment = session.get(PaymentRecord, request_record.payment_id)
        if payment is None:
            raise HTTPException(status_code=503, detail="Payment record is unavailable.")
        _authorize_order_access(payment.order_id, principal.access_token)
        return _response(payment)

    amount, currency = _order_total(payload.order_id, principal.access_token)
    outcome = provider.authorize(payload.payment_method_token)
    payment = PaymentRecord(
        order_id=payload.order_id,
        status=outcome.value,
        amount=amount,
        currency=currency,
    )
    session.add(payment)
    session.flush()
    session.add(
        PaymentRequestRecord(
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            payment_id=payment.id,
        )
    )
    if outcome.value == "CONFIRMED":
        confirmed_event = new_event(
            "PaymentConfirmed",
            "payments",
            {
                "paymentId": str(payment.id),
                "orderId": str(payment.order_id),
                "amount": {"amount": str(payment.amount), "currency": payment.currency},
            },
            correlation_id_var.get(),
        )
        session.add(OutboxEventRecord(**event_record_fields(confirmed_event)))
    session.commit()
    session.refresh(payment)
    return _response(payment)


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> PaymentResponse:
    payment = session.get(PaymentRecord, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found.")
    _authorize_order_access(payment.order_id, principal.access_token)
    return _response(payment)
