from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReservationItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID = Field(alias="productId")
    quantity: int = Field(ge=1, le=99)


class ReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(alias="orderId")
    items: list[ReservationItemRequest] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def unique_products(cls, items: list[ReservationItemRequest]) -> list[ReservationItemRequest]:
        ids = [item.product_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once in a reservation.")
        return items


class StockUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity_on_hand: int = Field(alias="quantityOnHand", ge=0)


class AvailabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID = Field(serialization_alias="productId")
    quantity_available: int = Field(serialization_alias="quantityAvailable")
    in_stock: bool = Field(serialization_alias="inStock")


class ReservationItemResponse(BaseModel):
    product_id: UUID = Field(serialization_alias="productId")
    quantity: int


class ReservationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reservation_id: UUID = Field(serialization_alias="reservationId")
    order_id: UUID = Field(serialization_alias="orderId")
    status: str
    expires_at: datetime = Field(serialization_alias="expiresAt")
    items: list[ReservationItemResponse]
