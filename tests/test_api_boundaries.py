from collections.abc import Iterator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _sqlite_database(
    base: type[DeclarativeBase],
) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_catalog_product_create_search_and_detail_use_api_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-signing-secret-with-at-least-32-bytes")
    import catalog.api.router as catalog_router
    from catalog.infrastructure.database import Base
    from catalog.main import app
    from service_common.identity import issue_access_token

    engine, sessions = _sqlite_database(Base)
    customer_token = issue_access_token(uuid4(), "catalog-customer", 300)
    operator_token = issue_access_token(uuid4(), "catalog-operator", 300, role="operator")

    def override_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[catalog_router.get_session] = override_session
    try:
        with TestClient(app) as client:
            forbidden = client.post(
                "/v1/categories",
                headers={"Authorization": f"Bearer {customer_token}"},
                json={"name": "Unauthorized", "slug": "unauthorized"},
            )
            assert forbidden.status_code == 403

            category_response = client.post(
                "/v1/categories",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"name": "Tea", "slug": "tea"},
            )
            assert category_response.status_code == 201
            product_response = client.post(
                "/v1/products",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={
                    "name": "Green Tea",
                    "description": "Loose leaf tea",
                    "price": {"amount": "8.50", "currency": "USD"},
                    "categoryId": category_response.json()["id"],
                    "imageUrl": "https://images.example/green-tea.jpg",
                },
            )
            assert product_response.status_code == 201
            product = product_response.json()
            assert product["category"] == "Tea"
            assert product["price"] == {"amount": "8.5000", "currency": "USD"}
            assert product["imageUrl"] == "https://images.example/green-tea.jpg"

            listed = client.get("/v1/products?q=tea&categoryId=" + category_response.json()["id"])
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["items"]] == [product["id"]]
            detail = client.get(f"/v1/products/{product['id']}")
            assert detail.status_code == 200
            assert detail.json()["id"] == product["id"]

            invalid = client.post(
                "/v1/products",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"name": "x", "price": {"amount": "-1", "currency": "usd"}},
            )
            assert invalid.status_code == 422
            assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

            numeric_amount = client.post(
                "/v1/products",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"name": "Numeric amount", "price": {"amount": 8.5, "currency": "USD"}},
            )
            assert numeric_amount.status_code == 422
    finally:
        app.dependency_overrides.pop(catalog_router.get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_cart_api_enforces_user_ownership_and_propagates_correlation_id(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-only-signing-secret-with-at-least-32-bytes")
    import orders.api.router as orders_router
    from orders.infrastructure.database import Base
    from orders.infrastructure.models import OrderRecord
    from orders.main import app
    from service_common.identity import issue_access_token

    product_id = uuid4()

    class FakeCatalogClient:
        def get_product(self, requested_id):
            assert requested_id == product_id
            return {
                "name": "Green Tea",
                "sellable": True,
                "price": {"amount": "8.50", "currency": "USD"},
            }

    engine, sessions = _sqlite_database(Base)
    first_user, other_user = uuid4(), uuid4()

    def override_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[orders_router.get_session] = override_session
    monkeypatch.setattr(orders_router, "CatalogClient", FakeCatalogClient)
    first_token = issue_access_token(first_user, "first", 300)
    other_token = issue_access_token(other_user, "other", 300)
    correlation_id = str(uuid4())
    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/carts",
                headers={
                    "Authorization": f"Bearer {first_token}",
                    "X-Correlation-ID": correlation_id,
                },
            )
            assert created.status_code == 201
            cart_id = created.json()["id"]
            assert created.headers["X-Correlation-ID"] == correlation_id

            added = client.post(
                f"/v1/carts/{cart_id}/items",
                headers={"Authorization": f"Bearer {first_token}"},
                json={"productId": str(product_id), "quantity": 2},
            )
            assert added.status_code == 200
            assert added.json()["items"][0]["quantity"] == 2
            assert added.json()["subtotal"] == {"amount": "17.0000", "currency": "USD"}

            quantity_updated = client.put(
                f"/v1/carts/{cart_id}/items/{product_id}",
                headers={"Authorization": f"Bearer {first_token}"},
                json={"quantity": 1},
            )
            assert quantity_updated.status_code == 200
            assert quantity_updated.json()["items"][0]["quantity"] == 1
            assert quantity_updated.json()["subtotal"] == {
                "amount": "8.5000",
                "currency": "USD",
            }

            owner_read = client.get(
                f"/v1/carts/{cart_id}", headers={"Authorization": f"Bearer {first_token}"}
            )
            assert owner_read.status_code == 200
            other_read = client.get(
                f"/v1/carts/{cart_id}", headers={"Authorization": f"Bearer {other_token}"}
            )
            assert other_read.status_code == 404

            order_id = uuid4()
            with sessions() as session:
                session.add(
                    OrderRecord(
                        id=order_id,
                        user_id=first_user,
                        status="PAID",
                        total_amount="8.50",
                        currency="USD",
                    )
                )
                session.commit()
            owner_order = client.get(
                f"/v1/orders/{order_id}", headers={"Authorization": f"Bearer {first_token}"}
            )
            assert owner_order.status_code == 200
            other_order = client.get(
                f"/v1/orders/{order_id}", headers={"Authorization": f"Bearer {other_token}"}
            )
            assert other_order.status_code == 404
    finally:
        app.dependency_overrides.pop(orders_router.get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()
