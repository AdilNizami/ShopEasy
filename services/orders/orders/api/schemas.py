from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MoneyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class CartItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID = Field(alias="productId")
    quantity: int = Field(ge=1, le=99)


class CartItemQuantityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1, le=99)


class CartItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID = Field(serialization_alias="productId")
    name: str
    quantity: int
    unit_price: MoneyResponse = Field(serialization_alias="unitPrice")


class CartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: Literal["ACTIVE", "CHECKING_OUT", "CHECKED_OUT"]
    items: list[CartItemResponse]
    subtotal: MoneyResponse | None
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID = Field(serialization_alias="productId")
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=99)
    unit_price: MoneyResponse = Field(serialization_alias="unitPrice")
    line_total: MoneyResponse = Field(serialization_alias="lineTotal")


class OrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: Literal["PENDING_PAYMENT", "PAID", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED"]
    items: list[OrderItemResponse]
    total: MoneyResponse
    payment_id: UUID | None = Field(serialization_alias="paymentId")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class OrderStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(serialization_alias="orderId")
    status: Literal["PENDING_PAYMENT", "PAID", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED"]
    updated_at: datetime = Field(serialization_alias="updatedAt")


class OrderPageResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: str | None = Field(serialization_alias="nextCursor")


class ShippingAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(alias="postalCode", min_length=1, max_length=24)
    country: str = Field(pattern=r"^[A-Z]{2}$")


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_id: UUID = Field(alias="cartId")
    shipping_address: ShippingAddress = Field(alias="shippingAddress")
    payment_method_token: Literal["mock-success", "mock-failure"] = Field(
        alias="paymentMethodToken"
    )
