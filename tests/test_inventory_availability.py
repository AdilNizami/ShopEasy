from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from inventory.api.router import get_session
from inventory.infrastructure.database import Base
from inventory.main import app


@pytest.fixture
def inventory_client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_positive_stock_is_available_after_stock_update(inventory_client: TestClient) -> None:
    product_id = uuid4()

    updated = inventory_client.put(
        f"/v1/inventory/stock/{product_id}",
        json={"quantityOnHand": 7},
    )

    assert updated.status_code == 200
    assert updated.json() == {
        "productId": str(product_id),
        "quantityAvailable": 7,
        "inStock": True,
    }

    availability = inventory_client.get(f"/v1/inventory/availability/{product_id}")
    assert availability.status_code == 200
    assert availability.json() == updated.json()


def test_zero_stock_is_not_available(inventory_client: TestClient) -> None:
    product_id = uuid4()

    response = inventory_client.put(
        f"/v1/inventory/stock/{product_id}",
        json={"quantityOnHand": 0},
    )

    assert response.status_code == 200
    assert response.json() == {
        "productId": str(product_id),
        "quantityAvailable": 0,
        "inStock": False,
    }


def test_availability_excludes_stock_held_by_active_reservation(
    inventory_client: TestClient,
) -> None:
    product_id = uuid4()
    order_id = uuid4()

    stock_response = inventory_client.put(
        f"/v1/inventory/stock/{product_id}",
        json={"quantityOnHand": 8},
    )
    assert stock_response.status_code == 200

    reservation_response = inventory_client.post(
        "/v1/inventory/reservations",
        headers={"Idempotency-Key": f"reservation-{order_id}"},
        json={
            "orderId": str(order_id),
            "items": [{"productId": str(product_id), "quantity": 3}],
        },
    )
    assert reservation_response.status_code == 201
    assert reservation_response.json()["status"] == "RESERVED"

    availability = inventory_client.get(f"/v1/inventory/availability/{product_id}")
    assert availability.status_code == 200
    assert availability.json() == {
        "productId": str(product_id),
        "quantityAvailable": 5,
        "inStock": True,
    }


def test_negative_stock_update_is_rejected_without_changing_stock(
    inventory_client: TestClient,
) -> None:
    product_id = uuid4()

    response = inventory_client.put(
        f"/v1/inventory/stock/{product_id}",
        json={"quantityOnHand": -1},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    availability = inventory_client.get(f"/v1/inventory/availability/{product_id}")
    assert availability.status_code == 200
    assert availability.json()["quantityAvailable"] == 0
    assert availability.json()["inStock"] is False


def test_missing_stock_record_reports_zero_available(inventory_client: TestClient) -> None:
    product_id = uuid4()

    response = inventory_client.get(f"/v1/inventory/availability/{product_id}")

    assert response.status_code == 200
    assert response.json() == {
        "productId": str(product_id),
        "quantityAvailable": 0,
        "inStock": False,
    }


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/v1/inventory/availability/not-a-uuid", None),
        ("put", "/v1/inventory/stock/not-a-uuid", {"quantityOnHand": 2}),
    ],
)
def test_invalid_product_uuid_is_rejected(
    inventory_client: TestClient,
    method: str,
    path: str,
    body: dict[str, int] | None,
) -> None:
    response = inventory_client.request(method, path, json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

