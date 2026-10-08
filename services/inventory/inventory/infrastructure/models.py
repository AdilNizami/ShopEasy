from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inventory.infrastructure.database import Base


class StockRecord(Base):
    __tablename__ = "stock"
    __table_args__ = (CheckConstraint("on_hand >= 0", name="ck_stock_on_hand_nonnegative"),)

    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ReservationRecord(Base):
    __tablename__ = "reservations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RESERVED")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    items: Mapped[list[ReservationItemRecord]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan"
    )


class ReservationRequestRecord(Base):
    __tablename__ = "reservation_requests"

    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reservation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False
    )


class ReservationItemRecord(Base):
    __tablename__ = "reservation_items"
    __table_args__ = (
        UniqueConstraint("reservation_id", "product_id", name="uq_reservation_product"),
        CheckConstraint("quantity > 0", name="ck_reservation_quantity_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    reservation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reservation: Mapped[ReservationRecord] = relationship(back_populates="items")
