from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orders.infrastructure.database import Base


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_PAYMENT")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    items: Mapped[list[OrderLineRecord]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderLineRecord.id"
    )


class OrderLineRecord(Base):
    __tablename__ = "order_lines"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    order: Mapped[OrderRecord] = relationship(back_populates="items")


class CartRecord(Base):
    __tablename__ = "carts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    items: Mapped[list[CartItemRecord]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", order_by="CartItemRecord.product_id"
    )


class CartItemRecord(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "product_id", name="uq_cart_item_product"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    cart_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cart: Mapped[CartRecord] = relationship(back_populates="items")


class CheckoutRequestRecord(Base):
    __tablename__ = "checkout_requests"

    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    cart_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("carts.id"), nullable=False
    )
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    shipping_address: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    reservation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class OutboxEventRecord(Base):
    __tablename__ = "outbox_events"

    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    producer: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)


class InboxEventRecord(Base):
    __tablename__ = "inbox_events"

    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
