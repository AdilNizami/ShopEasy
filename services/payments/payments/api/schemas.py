from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MoneyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(alias="orderId")
    payment_method_token: Literal["mock-success", "mock-failure"] = Field(
        alias="paymentMethodToken"
    )


class PaymentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    order_id: UUID = Field(serialization_alias="orderId")
    status: str
    amount: MoneyResponse
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
