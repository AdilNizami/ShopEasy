from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from orders.infrastructure.database import Base
from orders.infrastructure.models import CartItemRecord, CartRecord, OutboxEventRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.mark.parametrize(
    ("token", "expected_status", "expected_inventory_action", "cart_status"),
    [
        ("mock-success", "PAID", "commit", "CHECKED_OUT"),
        ("mock-failure", "CANCELLED", "release", "ACTIVE"),
    ],
)
def test_checkout_and_payment_event_complete_order_asynchronously(
    monkeypatch: pytest.MonkeyPatch,
    token: str,
    expected_status: str,
    expected_inventory_action: str,
    cart_status: str,
) -> None:
    import orders.api.router as order_router
    import orders.application.event_handlers as event_handlers
    from orders.main import app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    cart_id = uuid4()
    product_id = uuid4()
    with Session(engine, expire_on_commit=False) as session:
        cart = CartRecord(id=cart_id, status="ACTIVE")
        cart.items.append(
            CartItemRecord(
                product_id=product_id,
                name="Demo product",
                quantity=2,
                unit_amount="12.50",
                currency="USD",
            )
        )
        session.add(cart)
        session.commit()

    inventory_calls: list[str] = []
    payment_calls: list[str] = []
    reservation_id = uuid4()
    payment_id = uuid4()

    class FakeCatalogClient:
        def get_product(self, requested_id: UUID) -> dict[str, object]:
            assert requested_id == product_id
            return {
                "name": "Demo product",
                "sellable": True,
                "price": {"amount": "12.50", "currency": "USD"},
            }

    class FakeInventoryClient:
        def reserve(self, order_id: UUID, items: list[dict[str, object]]) -> dict[str, str]:
            assert len(items) == 1
            assert items[0]["quantity"] == 2
            inventory_calls.append("reserve")
            return {"reservationId": str(reservation_id)}

        def commit(self, requested_id: UUID) -> dict[str, str]:
            assert requested_id == reservation_id
            inventory_calls.append("commit")
            return {}

        def release(self, requested_id: UUID) -> dict[str, str]:
            assert requested_id == reservation_id
            inventory_calls.append("release")
            return {}

    class FakePaymentClient:
        def create(self, order_id: UUID, payment_method_token: str) -> dict[str, str]:
            assert order_id
            payment_calls.append(payment_method_token)
            return {
                "id": str(payment_id),
                "status": "CONFIRMED" if payment_method_token == "mock-success" else "FAILED",
            }

    def override_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    monkeypatch.setattr(order_router, "CatalogClient", FakeCatalogClient)
    monkeypatch.setattr(order_router, "InventoryClient", FakeInventoryClient)
    monkeypatch.setattr(event_handlers, "InventoryClient", FakeInventoryClient)
    monkeypatch.setattr(order_router, "PaymentClient", FakePaymentClient)
    app.dependency_overrides[order_router.get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/checkout",
                headers={"Idempotency-Key": "phase3-checkout"},
                json={
                    "cartId": str(cart_id),
                    "shippingAddress": {
                        "name": "Demo Buyer",
                        "line1": "1 Main Street",
                        "city": "Example",
                        "postalCode": "00000",
                        "country": "US",
                    },
                    "paymentMethodToken": token,
                },
            )
            assert response.status_code == 201
            assert response.json()["status"] == (
                "PENDING_PAYMENT" if expected_status == "PAID" else expected_status
            )
            assert response.json()["total"] == {"amount": "25.0000", "currency": "USD"}

            if expected_status == "PAID":
                from datetime import UTC, datetime

                event_handlers.consume_order_event(
                    {
                        "eventId": str(uuid4()),
                        "eventType": "PaymentConfirmed",
                        "version": 1,
                        "occurredAt": datetime.now(UTC).isoformat(),
                        "producer": "payments",
                        "data": {
                            "paymentId": str(payment_id),
                            "orderId": response.json()["id"],
                            "amount": {"amount": "25.0000", "currency": "USD"},
                        },
                    },
                    sessions=test_sessions,
                )

            replay = client.post(
                "/v1/checkout",
                headers={"Idempotency-Key": "phase3-checkout"},
                json={
                    "cartId": str(cart_id),
                    "shippingAddress": {
                        "name": "Demo Buyer",
                        "line1": "1 Main Street",
                        "city": "Example",
                        "postalCode": "00000",
                        "country": "US",
                    },
                    "paymentMethodToken": token,
                },
            )
            assert replay.status_code == 201
            assert replay.json()["id"] == response.json()["id"]
            assert replay.json()["status"] == expected_status
        with Session(engine) as session:
            assert session.get(CartRecord, cart_id).status == cart_status
            placed = list(
                session.scalars(
                    select(OutboxEventRecord).where(OutboxEventRecord.event_type == "OrderPlaced")
                )
            )
            assert len(placed) == 1
            assert placed[0].correlation_id is not None
    finally:
        app.dependency_overrides.pop(order_router.get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert inventory_calls == [
        "reserve",
        "commit" if expected_inventory_action == "commit" else "release",
    ]
    assert payment_calls == [token]
