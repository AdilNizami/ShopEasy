from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from service_common.schemas import ErrorResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from inventory.api.schemas import (
    AvailabilityResponse,
    ReservationItemResponse,
    ReservationRequest,
    ReservationResponse,
    StockUpdateRequest,
)
from inventory.domain.rules import InsufficientStock, available_quantity, ensure_available
from inventory.infrastructure.config import settings
from inventory.infrastructure.database import SessionLocal
from inventory.infrastructure.models import (
    ReservationItemRecord,
    ReservationRecord,
    ReservationRequestRecord,
    StockRecord,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def get_session():
    with SessionLocal() as session:
        yield session


def _reserved_quantity(session: Session, product_id: UUID, now: datetime) -> int:
    value = session.scalar(
        select(func.coalesce(func.sum(ReservationItemRecord.quantity), 0))
        .join(ReservationRecord, ReservationRecord.id == ReservationItemRecord.reservation_id)
        .where(
            ReservationItemRecord.product_id == product_id,
            ReservationRecord.status == "RESERVED",
            ReservationRecord.expires_at > now,
        )
    )
    return int(value or 0)


def _reservation_response(record: ReservationRecord) -> ReservationResponse:
    return ReservationResponse(
        reservation_id=record.id,
        order_id=record.order_id,
        status=record.status,
        expires_at=record.expires_at,
        items=[
            ReservationItemResponse(product_id=item.product_id, quantity=item.quantity)
            for item in record.items
        ],
    )


def _fingerprint(payload: ReservationRequest) -> str:
    document = {
        "orderId": str(payload.order_id),
        "items": sorted(
            [
                {"productId": str(item.product_id), "quantity": item.quantity}
                for item in payload.items
            ],
            key=lambda item: item["productId"],
        ),
    }
    return hashlib.sha256(json.dumps(document, separators=(",", ":")).encode()).hexdigest()


@router.put("/stock/{product_id}", response_model=AvailabilityResponse)
def set_stock(
    product_id: UUID,
    payload: StockUpdateRequest,
    session: Session = Depends(get_session),
) -> AvailabilityResponse:
    stock = session.scalar(
        select(StockRecord).where(StockRecord.product_id == product_id).with_for_update()
    )
    if stock is None:
        stock = StockRecord(product_id=product_id, on_hand=payload.quantity_on_hand)
        session.add(stock)
    else:
        reserved = _reserved_quantity(session, product_id, datetime.now(UTC))
        if payload.quantity_on_hand < reserved:
            raise HTTPException(
                status_code=409,
                detail="Quantity on hand cannot be lower than active reservations.",
            )
        stock.on_hand = payload.quantity_on_hand
    session.commit()
    reserved = _reserved_quantity(session, product_id, datetime.now(UTC))
    available = available_quantity(payload.quantity_on_hand, reserved)
    return AvailabilityResponse(
        product_id=product_id,
        quantity_available=available,
        in_stock=available > 0,
    )


@router.get("/availability/{product_id}", response_model=AvailabilityResponse)
def get_availability(
    product_id: UUID, session: Session = Depends(get_session)
) -> AvailabilityResponse:
    now = datetime.now(UTC)
    stock = session.get(StockRecord, product_id)
    on_hand = stock.on_hand if stock else 0
    available = available_quantity(on_hand, _reserved_quantity(session, product_id, now))
    return AvailabilityResponse(
        product_id=product_id,
        quantity_available=available,
        in_stock=available > 0,
    )


@router.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        503: {
            "model": ErrorResponse,
            "description": "Stock reservation is temporarily unavailable.",
        }
    },
)
def reserve_stock(
    payload: ReservationRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    session: Session = Depends(get_session),
) -> ReservationResponse:
    fingerprint = _fingerprint(payload)
    existing_request = session.get(ReservationRequestRecord, idempotency_key)
    if existing_request is not None:
        if existing_request.fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key was reused.")
        existing = session.scalar(
            select(ReservationRecord)
            .where(ReservationRecord.id == existing_request.reservation_id)
            .options(selectinload(ReservationRecord.items))
        )
        if existing is None:
            raise HTTPException(status_code=503, detail="Reservation record is unavailable.")
        return _reservation_response(existing)

    product_ids = sorted(item.product_id for item in payload.items)
    stock_rows = session.scalars(
        select(StockRecord)
        .where(StockRecord.product_id.in_(product_ids))
        .order_by(StockRecord.product_id)
        .with_for_update()
    ).all()
    stock_by_id = {row.product_id: row for row in stock_rows}

    # Recheck after row locks so concurrent requests for the same order are idempotent.
    existing_request = session.get(ReservationRequestRecord, idempotency_key)
    if existing_request is not None:
        if existing_request.fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key was reused.")
        existing = session.scalar(
            select(ReservationRecord)
            .where(ReservationRecord.id == existing_request.reservation_id)
            .options(selectinload(ReservationRecord.items))
        )
        if existing is None:
            raise HTTPException(status_code=503, detail="Reservation record is unavailable.")
        return _reservation_response(existing)

    existing_order = session.scalar(
        select(ReservationRecord)
        .where(ReservationRecord.order_id == payload.order_id)
        .options(selectinload(ReservationRecord.items))
    )
    if existing_order is not None:
        existing_payload = {(item.product_id, item.quantity) for item in existing_order.items}
        requested_payload = {(item.product_id, item.quantity) for item in payload.items}
        if existing_payload != requested_payload:
            raise HTTPException(
                status_code=409, detail="Order already has a different reservation."
            )
        session.add(
            ReservationRequestRecord(
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                reservation_id=existing_order.id,
            )
        )
        session.commit()
        return _reservation_response(existing_order)

    now = datetime.now(UTC)
    try:
        for item in payload.items:
            stock = stock_by_id.get(item.product_id)
            ensure_available(
                stock.on_hand if stock else 0,
                _reserved_quantity(session, item.product_id, now),
                item.quantity,
            )
    except InsufficientStock as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Insufficient stock.") from exc

    reservation = ReservationRecord(
        order_id=payload.order_id,
        status="RESERVED",
        expires_at=now + timedelta(seconds=settings.reservation_ttl_seconds),
        items=[
            ReservationItemRecord(product_id=item.product_id, quantity=item.quantity)
            for item in payload.items
        ],
    )
    session.add(reservation)
    session.flush()
    session.add(
        ReservationRequestRecord(
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            reservation_id=reservation.id,
        )
    )
    session.commit()
    return _reservation_response(reservation)


def _change_reservation(
    reservation_id: UUID,
    session: Session,
    terminal_status: str,
) -> ReservationResponse:
    record = session.scalar(
        select(ReservationRecord)
        .where(ReservationRecord.id == reservation_id)
        .options(selectinload(ReservationRecord.items))
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    if record.status == terminal_status:
        return _reservation_response(record)
    if record.status == "COMMITTED":
        raise HTTPException(status_code=409, detail="Committed stock cannot be released.")
    if record.status in {"RELEASED", "EXPIRED"}:
        raise HTTPException(status_code=409, detail="Reservation is no longer active.")

    now = datetime.now(UTC)
    if terminal_status == "COMMITTED":
        if record.expires_at <= now:
            record.status = "EXPIRED"
            session.commit()
            raise HTTPException(status_code=409, detail="Reservation has expired.")
        product_ids = sorted(item.product_id for item in record.items)
        stocks = session.scalars(
            select(StockRecord)
            .where(StockRecord.product_id.in_(product_ids))
            .order_by(StockRecord.product_id)
            .with_for_update()
        ).all()
        stock_by_id = {item.product_id: item for item in stocks}
        for item in record.items:
            stock = stock_by_id.get(item.product_id)
            if stock is None or stock.on_hand < item.quantity:
                raise HTTPException(
                    status_code=409, detail="Reserved stock is no longer available."
                )
        for item in record.items:
            stock_by_id[item.product_id].on_hand -= item.quantity
    elif record.expires_at <= now:
        record.status = "EXPIRED"
        session.commit()
        return _reservation_response(record)
    else:
        record.status = terminal_status

    session.commit()
    return _reservation_response(record)


@router.post("/reservations/{reservation_id}/commit", response_model=ReservationResponse)
def commit_reservation(
    reservation_id: UUID, session: Session = Depends(get_session)
) -> ReservationResponse:
    return _change_reservation(reservation_id, session, "COMMITTED")


@router.post("/reservations/{reservation_id}/release", response_model=ReservationResponse)
def release_reservation(
    reservation_id: UUID, session: Session = Depends(get_session)
) -> ReservationResponse:
    return _change_reservation(reservation_id, session, "RELEASED")
