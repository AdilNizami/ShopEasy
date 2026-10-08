from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PaymentAttempt:
    id: UUID
    order_id: UUID
    status: PaymentStatus
    amount: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime
