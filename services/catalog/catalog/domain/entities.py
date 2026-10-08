from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class Product:
    id: UUID
    name: str
    description: str
    amount: Decimal
    currency: str
    sellable: bool
    category_id: UUID | None
    image_url: str | None
    updated_at: datetime
