from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class StockLevel:
    product_id: UUID
    on_hand: int
    reserved: int


@dataclass(frozen=True)
class Reservation:
    id: UUID
    order_id: UUID
    status: ReservationStatus
    expires_at: datetime
