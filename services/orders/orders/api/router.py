from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from service_common.events import event_record_fields, new_event
from service_common.identity import Principal, get_current_principal
from service_common.logging import correlation_id_var
from service_common.schemas import ErrorResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload as load

from orders.api.schemas import (
    CartItemRequest,
    CartItemQuantityRequest,
    CartItemResponse,
    CartResponse,
    CheckoutRequest,
    MoneyResponse,
    OrderItemResponse,
    OrderPageResponse,
    OrderResponse,
    OrderStatusResponse,
)
from orders.application.clients import CatalogClient, InventoryClient, PaymentClient
from orders.domain.cart_rules import calculate_cart_total, updated_quantity
from orders.domain.entities import OrderStatus
from orders.domain.state import transition_order
from orders.infrastructure.database import SessionLocal
from orders.infrastructure.models import (
    CartItemRecord,
    CartRecord,
    CheckoutRequestRecord,
    OrderLineRecord,
    OrderRecord,
    OutboxEventRecord,
)

carts_router = APIRouter(prefix="/carts", tags=["Cart"])
checkout_router = APIRouter(prefix="/checkout", tags=["Checkout"])
orders_router = APIRouter(prefix="/orders", tags=["Orders"])


def get_session():
    with SessionLocal() as session:
        yield session


def _cart_response(cart: CartRecord) -> CartResponse:
    total, currency = calculate_cart_total(
        [(item.quantity, item.unit_amount, item.currency) for item in cart.items]
    )
    return CartResponse(
        id=cart.id,
        status=cart.status,
        items=[
            CartItemResponse(
                product_id=item.product_id,
                name=item.name,
                quantity=item.quantity,
                unit_price=MoneyResponse(amount=item.unit_amount, currency=item.currency),
            )
            for item in cart.items
        ],
        subtotal=MoneyResponse(amount=total, currency=currency) if currency else None,
        created_at=cart.created_at,
        updated_at=cart.updated_at,
    )


def _order_response(order: OrderRecord) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        status=order.status,
        items=[
            OrderItemResponse(
                product_id=item.product_id,
                name=item.name,
                quantity=item.quantity,
                unit_price=MoneyResponse(amount=item.unit_amount, currency=item.currency),
                line_total=MoneyResponse(
                    amount=item.unit_amount * item.quantity,
                    currency=item.currency,
                ),
            )
            for item in order.items
        ],
        total=MoneyResponse(amount=order.total_amount, currency=order.currency),
        payment_id=order.payment_id,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _checkout_fingerprint(payload: CheckoutRequest) -> str:
    document = {
        "cartId": str(payload.cart_id),
        "shippingAddress": payload.shipping_address.model_dump(by_alias=True, exclude_none=True),
        "paymentMethodTokenHash": hashlib.sha256(payload.payment_method_token.encode()).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _find_checkout(
    session: Session, idempotency_key: str, user_id: UUID
) -> tuple[CheckoutRequestRecord, OrderRecord] | None:
    checkout = session.get(CheckoutRequestRecord, idempotency_key)
    if checkout is None:
        return None
    order = session.scalar(
        select(OrderRecord)
        .where(OrderRecord.id == checkout.order_id)
        .options(load(OrderRecord.items))
    )
    if order is None:
        raise HTTPException(status_code=503, detail="Checkout record is inconsistent.")
    if order.user_id != user_id:
        raise HTTPException(status_code=404, detail="Checkout not found.")
    return checkout, order


@carts_router.post("", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
def create_cart(
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CartResponse:
    cart = CartRecord(status="ACTIVE", user_id=principal.user_id)
    session.add(cart)
    session.commit()
    session.refresh(cart)
    return _cart_response(cart)


@carts_router.get("/{cart_id}", response_model=CartResponse)
def get_cart(
    cart_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CartResponse:
    cart = session.scalar(
        select(CartRecord)
        .where(CartRecord.id == cart_id, CartRecord.user_id == principal.user_id)
        .options(load(CartRecord.items))
    )
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found.")
    return _cart_response(cart)


@carts_router.post("/{cart_id}/items", response_model=CartResponse, status_code=status.HTTP_200_OK)
def add_cart_item(
    cart_id: UUID,
    payload: CartItemRequest,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CartResponse:
    product = CatalogClient().get_product(payload.product_id)
    price = product.get("price", {})
    try:
        amount = Decimal(str(price["amount"]))
        currency = str(price["currency"])
        if amount < 0 or len(currency) != 3:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Catalog returned invalid price data.") from exc

    cart = session.scalar(
        select(CartRecord)
        .where(CartRecord.id == cart_id, CartRecord.user_id == principal.user_id)
        .options(load(CartRecord.items))
        .with_for_update()
    )
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found.")
    if cart.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Cart is not open for changes.")
    if not product.get("sellable", False):
        raise HTTPException(status_code=409, detail="Product is not sellable.")
    if cart.items and any(item.currency != currency for item in cart.items):
        raise HTTPException(status_code=409, detail="All cart items must use the same currency.")

    item = next((row for row in cart.items if row.product_id == payload.product_id), None)
    try:
        quantity = updated_quantity(item.quantity if item else 0, payload.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        item = CartItemRecord(
            product_id=payload.product_id,
            name=str(product["name"]),
            quantity=quantity,
            unit_amount=amount,
            currency=currency,
        )
        cart.items.append(item)
    else:
        item.name = str(product["name"])
        item.quantity = quantity
        item.unit_amount = amount
    cart.updated_at = datetime.now(UTC)
    session.commit()
    return _cart_response(cart)


@carts_router.delete("/{cart_id}/items/{product_id}", response_model=CartResponse)
def remove_cart_item(
    cart_id: UUID,
    product_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CartResponse:
    cart = session.scalar(
        select(CartRecord)
        .where(CartRecord.id == cart_id, CartRecord.user_id == principal.user_id)
        .options(load(CartRecord.items))
        .with_for_update()
    )
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found.")
    if cart.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Cart is not open for changes.")
    item = next((row for row in cart.items if row.product_id == product_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found.")
    cart.items.remove(item)
    cart.updated_at = datetime.now(UTC)
    session.commit()
    return _cart_response(cart)


@carts_router.put("/{cart_id}/items/{product_id}", response_model=CartResponse)
def set_cart_item_quantity(
    cart_id: UUID,
    product_id: UUID,
    payload: CartItemQuantityRequest,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CartResponse:
    product = CatalogClient().get_product(product_id)
    price = product.get("price", {})
    try:
        amount = Decimal(str(price["amount"]))
        currency = str(price["currency"])
        if amount < 0 or len(currency) != 3:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Catalog returned invalid price data.") from exc

    cart = session.scalar(
        select(CartRecord)
        .where(CartRecord.id == cart_id, CartRecord.user_id == principal.user_id)
        .options(load(CartRecord.items))
        .with_for_update()
    )
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found.")
    if cart.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Cart is not open for changes.")
    if not product.get("sellable", False):
        raise HTTPException(status_code=409, detail="Product is not sellable.")
    item = next((row for row in cart.items if row.product_id == product_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found.")
    if any(row.currency != currency for row in cart.items if row.product_id != product_id):
        raise HTTPException(status_code=409, detail="All cart items must use the same currency.")
    item.name = str(product["name"])
    item.quantity = payload.quantity
    item.unit_amount = amount
    item.currency = currency
    cart.updated_at = datetime.now(UTC)
    session.commit()
    return _cart_response(cart)


def _resume_checkout(
    session: Session,
    checkout: CheckoutRequestRecord,
    order: OrderRecord,
    payment_method_token: str,
    access_token: str,
) -> OrderResponse:
    if order.status != OrderStatus.PENDING_PAYMENT.value:
        return _order_response(order)

    inventory_client = InventoryClient()
    reservation_id = checkout.reservation_id
    if reservation_id is None:
        try:
            reservation = inventory_client.reserve(
                order.id,
                [
                    {"productId": str(item.product_id), "quantity": item.quantity}
                    for item in order.items
                ],
            )
        except HTTPException as exc:
            if exc.status_code == 409:
                order.status = transition_order(order.status, OrderStatus.CANCELLED)
                order.updated_at = datetime.now(UTC)
                cart = session.get(CartRecord, checkout.cart_id)
                if cart is not None:
                    cart.status = "ACTIVE"
                session.commit()
            raise
        try:
            reservation_id = UUID(reservation["reservationId"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=502, detail="Inventory returned invalid reservation data."
            ) from exc
        checkout.reservation_id = reservation_id
        session.commit()

    payment = PaymentClient().create(order.id, payment_method_token, access_token)
    try:
        payment_id = UUID(payment["id"])
        payment_status = payment["status"]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Payments returned invalid payment data."
        ) from exc
    order.payment_id = payment_id
    order.updated_at = datetime.now(UTC)
    session.commit()

    if payment_status == "FAILED":
        inventory_client.release(reservation_id)
        order.status = transition_order(order.status, OrderStatus.CANCELLED)
        cart = session.get(CartRecord, checkout.cart_id)
        if cart is not None:
            cart.status = "ACTIVE"
    elif payment_status == "CONFIRMED":
        # PaymentConfirmed is the TELL that Orders consumes asynchronously.
        # Inventory commit and PAID transition happen in that event handler.
        pass
    else:
        raise HTTPException(status_code=502, detail="Payments returned an unknown outcome.")
    order.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(order)
    return _order_response(order)


@checkout_router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse, "description": "Cart or stock conflicts with checkout."},
        503: {"model": ErrorResponse, "description": "A checkout dependency is unavailable."},
    },
)
def checkout(
    payload: CheckoutRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> OrderResponse:
    fingerprint = _checkout_fingerprint(payload)
    existing = _find_checkout(session, idempotency_key, principal.user_id)
    if existing is not None:
        checkout_record, order = existing
        if checkout_record.fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key was reused.")
        return _resume_checkout(
            session,
            checkout_record,
            order,
            payload.payment_method_token,
            principal.access_token,
        )

    cart = session.scalar(
        select(CartRecord)
        .where(CartRecord.id == payload.cart_id, CartRecord.user_id == principal.user_id)
        .options(load(CartRecord.items))
    )
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found.")
    if cart.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Cart is not available for checkout.")
    if not cart.items:
        raise HTTPException(status_code=409, detail="Cart is empty.")
    cart_snapshot = [(item.product_id, item.quantity) for item in cart.items]
    session.rollback()

    product_data: dict[UUID, dict] = {}
    for product_id, _ in cart_snapshot:
        product_data[product_id] = CatalogClient().get_product(product_id)
    currencies = {str(product["price"]["currency"]) for product in product_data.values()}
    if len(currencies) != 1:
        raise HTTPException(status_code=409, detail="All order items must use the same currency.")
    currency = currencies.pop()

    locked_cart = session.scalar(
        select(CartRecord)
        .where(CartRecord.id == payload.cart_id, CartRecord.user_id == principal.user_id)
        .options(load(CartRecord.items))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_cart is None:
        raise HTTPException(status_code=404, detail="Cart not found.")
    existing = _find_checkout(session, idempotency_key, principal.user_id)
    if existing is not None:
        checkout_record, order = existing
        if checkout_record.fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key was reused.")
        return _resume_checkout(
            session,
            checkout_record,
            order,
            payload.payment_method_token,
            principal.access_token,
        )
    if locked_cart.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Cart is not available for checkout.")
    if [(item.product_id, item.quantity) for item in locked_cart.items] != cart_snapshot:
        raise HTTPException(
            status_code=409, detail="Cart changed during checkout. Retry the request."
        )

    order_items = []
    total = Decimal("0")
    for product_id, quantity in cart_snapshot:
        product = product_data[product_id]
        if product.get("sellable") is not True:
            raise HTTPException(status_code=409, detail="A cart product is no longer sellable.")
        try:
            amount = Decimal(str(product["price"]["amount"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=502, detail="Catalog returned invalid price data."
            ) from exc
        total += amount * quantity
        order_items.append(
            OrderLineRecord(
                product_id=product_id,
                name=str(product["name"]),
                quantity=quantity,
                unit_amount=amount,
                currency=currency,
            )
        )
    order = OrderRecord(
        user_id=principal.user_id,
        status=OrderStatus.PENDING_PAYMENT.value,
        total_amount=total,
        currency=currency,
        items=order_items,
    )
    locked_cart.status = "CHECKING_OUT"
    locked_cart.updated_at = datetime.now(UTC)
    session.add(order)
    session.flush()
    checkout_record = CheckoutRequestRecord(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        cart_id=locked_cart.id,
        order_id=order.id,
        shipping_address=payload.shipping_address.model_dump(by_alias=True, exclude_none=True),
    )
    session.add(checkout_record)
    placed_event = new_event(
        "OrderPlaced",
        "orders",
        {
            "orderId": str(order.id),
            "total": {"amount": str(order.total_amount), "currency": order.currency},
            "items": [
                {
                    "productId": str(item.product_id),
                    "name": item.name,
                    "quantity": item.quantity,
                    "unitPrice": {
                        "amount": str(item.unit_amount),
                        "currency": item.currency,
                    },
                }
                for item in order.items
            ],
        },
        correlation_id_var.get(),
    )
    session.add(OutboxEventRecord(**event_record_fields(placed_event)))
    session.commit()
    session.refresh(order)
    session.refresh(checkout_record)
    return _resume_checkout(
        session,
        checkout_record,
        order,
        payload.payment_method_token,
        principal.access_token,
    )


@orders_router.get("", response_model=OrderPageResponse)
def list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=512),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> OrderPageResponse:
    statement = (
        select(OrderRecord)
        .where(OrderRecord.user_id == principal.user_id)
        .options(load(OrderRecord.items))
        .order_by(OrderRecord.id)
    )
    if cursor:
        try:
            after_id = UUID(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid cursor.") from exc
        statement = statement.where(OrderRecord.id > after_id)
    records = list(session.scalars(statement.limit(limit + 1)))
    page = records[:limit]
    return OrderPageResponse(
        items=[_order_response(record) for record in page],
        next_cursor=str(page[-1].id) if len(records) > limit and page else None,
    )


@orders_router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> OrderResponse:
    record = session.scalar(
        select(OrderRecord)
        .where(OrderRecord.id == order_id, OrderRecord.user_id == principal.user_id)
        .options(load(OrderRecord.items))
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    return _order_response(record)


@orders_router.get("/{order_id}/status", response_model=OrderStatusResponse)
def get_order_status(
    order_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> OrderStatusResponse:
    record = session.scalar(
        select(OrderRecord).where(
            OrderRecord.id == order_id, OrderRecord.user_id == principal.user_id
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    return OrderStatusResponse(
        order_id=record.id,
        status=record.status,
        updated_at=record.updated_at,
    )
