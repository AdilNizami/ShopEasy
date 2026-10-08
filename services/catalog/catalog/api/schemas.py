from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class MoneyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=5000)
    price: MoneyResponse = Field(validation_alias="price_data")
    sellable: bool
    category_id: UUID | None = Field(default=None, serialization_alias="categoryId")
    category: str | None = None
    image_url: str | None = Field(default=None, serialization_alias="imageUrl")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ProductPageResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: str | None = Field(serialization_alias="nextCursor")


class MoneyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("amount", mode="before")
    @classmethod
    def require_decimal_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("Money amounts must be decimal strings.")
        return value


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    price: MoneyInput
    sellable: bool = True
    category_id: UUID | None = Field(default=None, alias="categoryId")
    image_url: AnyHttpUrl | None = Field(default=None, alias="imageUrl", max_length=2048)


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    slug: str
