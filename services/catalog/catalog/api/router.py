from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from catalog.api.schemas import (
    CategoryCreateRequest,
    CategoryResponse,
    MoneyResponse,
    ProductCreateRequest,
    ProductPageResponse,
    ProductResponse,
)
from catalog.infrastructure.database import SessionLocal
from catalog.infrastructure.models import CategoryRecord, ProductDetailsRecord, ProductRecord

products_router = APIRouter(prefix="/products", tags=["Products"])
categories_router = APIRouter(prefix="/categories", tags=["Categories"])


def get_session():
    with SessionLocal() as session:
        yield session


def product_response(
    product: ProductRecord,
    details: ProductDetailsRecord | None,
    category: CategoryRecord | None,
) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        price=MoneyResponse(amount=product.amount, currency=product.currency),
        sellable=product.sellable,
        category_id=details.category_id if details else None,
        category=category.name if category else None,
        image_url=details.image_url if details else None,
        updated_at=product.updated_at,
    )


@products_router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateRequest, session: Session = Depends(get_session)
) -> ProductResponse:
    category = None
    if payload.category_id is not None:
        category = session.get(CategoryRecord, payload.category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found.")

    product = ProductRecord(
        name=payload.name,
        description=payload.description,
        amount=payload.price.amount,
        currency=payload.price.currency,
        sellable=payload.sellable,
    )
    session.add(product)
    session.flush()
    details = ProductDetailsRecord(
        product_id=product.id,
        category_id=payload.category_id,
        image_url=str(payload.image_url) if payload.image_url is not None else None,
    )
    session.add(details)
    session.commit()
    session.refresh(product)
    return product_response(product, details, category)


@products_router.get("", response_model=ProductPageResponse)
def list_products(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=512),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    category_id: UUID | None = Query(default=None, alias="categoryId"),
    min_price: str | None = Query(default=None, alias="minPrice", pattern=r"^\d+(\.\d{1,4})?$"),
    max_price: str | None = Query(default=None, alias="maxPrice", pattern=r"^\d+(\.\d{1,4})?$"),
    session: Session = Depends(get_session),
) -> ProductPageResponse:
    statement = (
        select(ProductRecord, ProductDetailsRecord, CategoryRecord)
        .outerjoin(ProductDetailsRecord, ProductDetailsRecord.product_id == ProductRecord.id)
        .outerjoin(CategoryRecord, CategoryRecord.id == ProductDetailsRecord.category_id)
        .where(ProductRecord.sellable.is_(True))
        .order_by(ProductRecord.id)
    )
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            ProductRecord.name.ilike(pattern) | ProductRecord.description.ilike(pattern)
        )
    if category_id:
        statement = statement.where(ProductDetailsRecord.category_id == category_id)
    if min_price is not None and max_price is not None:
        if Decimal(min_price) > Decimal(max_price):
            raise HTTPException(status_code=422, detail="minPrice must not exceed maxPrice.")
    if min_price is not None:
        statement = statement.where(ProductRecord.amount >= Decimal(min_price))
    if max_price is not None:
        statement = statement.where(ProductRecord.amount <= Decimal(max_price))
    if cursor:
        try:
            after_id = UUID(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid cursor.") from exc
        statement = statement.where(ProductRecord.id > after_id)

    rows = list(session.execute(statement.limit(limit + 1)))
    page = rows[:limit]
    next_cursor = str(page[-1][0].id) if len(rows) > limit and page else None
    return ProductPageResponse(
        items=[product_response(*row) for row in page],
        next_cursor=next_cursor,
    )


@products_router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: UUID, session: Session = Depends(get_session)) -> ProductResponse:
    row = session.execute(
        select(ProductRecord, ProductDetailsRecord, CategoryRecord)
        .outerjoin(ProductDetailsRecord, ProductDetailsRecord.product_id == ProductRecord.id)
        .outerjoin(CategoryRecord, CategoryRecord.id == ProductDetailsRecord.category_id)
        .where(ProductRecord.id == product_id, ProductRecord.sellable.is_(True))
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product_response(*row)


@categories_router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreateRequest, session: Session = Depends(get_session)
) -> CategoryResponse:
    category = CategoryRecord(name=payload.name.strip(), slug=payload.slug)
    if not category.name:
        raise HTTPException(status_code=422, detail="Category name cannot be blank.")
    session.add(category)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Category name or slug already exists."
        ) from exc
    session.refresh(category)
    return CategoryResponse(id=category.id, name=category.name, slug=category.slug)


@categories_router.get("", response_model=list[CategoryResponse])
def list_categories(session: Session = Depends(get_session)) -> list[CategoryResponse]:
    categories = session.scalars(select(CategoryRecord).order_by(CategoryRecord.name)).all()
    return [CategoryResponse(id=row.id, name=row.name, slug=row.slug) for row in categories]
