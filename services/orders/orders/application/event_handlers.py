from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from service_common.events import event_record_fields, new_event, validate_event
from service_common.logging import correlation_id_var
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from orders.application.clients import InventoryClient
from orders.domain.entities import OrderStatus
from orders.domain.state import transition_order
from orders.infrastructure.database import SessionLocal
from orders.infrastructure.models import (
    CartRecord,
    CheckoutRequestRecord,
    InboxEventRecord,
    OrderRecord,
    OutboxEventRecord,
)

logger = logging.getLogger("shop_easy.orders.events")


def _handle_payment_confirmed(event: dict[str, Any], sessions=None) -> None:
    sessions = sessions or SessionLocal
    data = event["data"]
    order_id = UUID(data["orderId"])
    payment_id = UUID(data["paymentId"])
    amount = Decimal(data["amount"]["amount"])
    currency = data["amount"]["currency"]

    with sessions() as session:
        if session.get(InboxEventRecord, UUID(event["eventId"])):
            return
        order = session.scalar(
            select(OrderRecord)
            .where(OrderRecord.id == order_id)
            .options(selectinload(OrderRecord.items))
            .with_for_update()
        )
        if order is None:
            raise ValueError("PaymentConfirmed references an unknown order.")
        if amount != order.total_amount or currency != order.currency:
            raise ValueError("PaymentConfirmed amount does not match the order total.")
        if order.payment_id is not None and order.payment_id != payment_id:
            raise ValueError("PaymentConfirmed references a different payment attempt.")
        if order.status == OrderStatus.PENDING_PAYMENT.value:
            checkout = session.scalar(
                select(CheckoutRequestRecord).where(CheckoutRequestRecord.order_id == order_id)
            )
            if checkout is None or checkout.reservation_id is None:
                raise RuntimeError("Order has no inventory reservation to commit.")
            reservation_id = checkout.reservation_id
        elif order.status == OrderStatus.PAID.value:
            reservation_id = None
        else:
            raise ValueError("PaymentConfirmed cannot be applied to this order state.")
        session.rollback()

    token = correlation_id_var.set(event.get("correlationId", "-"))
    try:
        if reservation_id is not None:
            try:
                InventoryClient().commit(reservation_id)
            except HTTPException as exc:
                if exc.status_code == 409:
                    raise ValueError("Inventory reservation cannot be committed.") from exc
                raise
    finally:
        correlation_id_var.reset(token)

    with sessions() as session:
        if session.get(InboxEventRecord, UUID(event["eventId"])):
            return
        order = session.scalar(
            select(OrderRecord)
            .where(OrderRecord.id == order_id)
            .options(selectinload(OrderRecord.items))
            .with_for_update()
        )
        if order is None:
            raise ValueError("PaymentConfirmed references an unknown order.")
        if order.status == OrderStatus.PENDING_PAYMENT.value:
            order.payment_id = payment_id
            order.status = transition_order(order.status, OrderStatus.PAID)
            order.updated_at = datetime.now(UTC)
            checkout = session.scalar(
                select(CheckoutRequestRecord).where(CheckoutRequestRecord.order_id == order_id)
            )
            if checkout is not None:
                cart = session.get(CartRecord, checkout.cart_id)
                if cart is not None:
                    cart.status = "CHECKED_OUT"
                    cart.updated_at = datetime.now(UTC)
            session.add(
                OutboxEventRecord(
                    **event_record_fields(
                        new_event(
                            "OrderPaid",
                            "orders",
                            {
                                "orderId": str(order.id),
                                "paymentId": str(payment_id),
                                "total": {
                                    "amount": str(order.total_amount),
                                    "currency": order.currency,
                                },
                            },
                            event.get("correlationId"),
                        )
                    )
                )
            )
        elif order.status != OrderStatus.PAID.value or order.payment_id != payment_id:
            raise ValueError("Order state changed while processing PaymentConfirmed.")
        session.add(
            InboxEventRecord(
                event_id=UUID(event["eventId"]),
                event_type=event["eventType"],
                correlation_id=(
                    UUID(event["correlationId"]) if event.get("correlationId") else None
                ),
                processed_at=datetime.now(UTC),
            )
        )
        session.commit()
        logger.info("payment confirmation applied order_id=%s payment_id=%s", order_id, payment_id)


def _handle_shipping_event(event: dict[str, Any], sessions=None) -> None:
    sessions = sessions or SessionLocal
    order_id = UUID(event["data"]["orderId"])
    event_id = UUID(event["eventId"])
    with sessions() as session:
        if session.get(InboxEventRecord, event_id):
            return
        order = session.scalar(
            select(OrderRecord).where(OrderRecord.id == order_id).with_for_update()
        )
        if order is None:
            raise ValueError("Shipping event references an unknown order.")

        if event["eventType"] == "OrderShipped":
            if order.status == OrderStatus.PAID.value:
                order.status = transition_order(order.status, OrderStatus.PROCESSING)
            if order.status != OrderStatus.SHIPPED.value:
                order.status = transition_order(order.status, OrderStatus.SHIPPED)
        else:
            if order.status != OrderStatus.DELIVERED.value:
                order.status = transition_order(order.status, OrderStatus.DELIVERED)
        order.updated_at = datetime.now(UTC)
        session.add(
            InboxEventRecord(
                event_id=event_id,
                event_type=event["eventType"],
                correlation_id=(
                    UUID(event["correlationId"]) if event.get("correlationId") else None
                ),
                processed_at=datetime.now(UTC),
            )
        )
        session.commit()


def consume_order_event(event: dict[str, Any], sessions=None) -> None:
    validate_event(event)
    token = correlation_id_var.set(event.get("correlationId", "-"))
    try:
        event_type = event["eventType"]
        if event_type == "PaymentConfirmed":
            _handle_payment_confirmed(event, sessions)
        elif event_type in {"OrderShipped", "OrderDelivered"}:
            _handle_shipping_event(event, sessions)
        else:
            raise ValueError(f"Orders does not consume {event_type}.")
    finally:
        correlation_id_var.reset(token)
