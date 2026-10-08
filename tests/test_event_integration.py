import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from jsonschema import Draft202012Validator
from orders.infrastructure.database import Base as OrdersBase
from orders.infrastructure.models import (
    CheckoutRequestRecord,
    InboxEventRecord,
    OrderRecord,
)
from orders.infrastructure.models import (
    OutboxEventRecord as OrdersOutboxRecord,
)
from payments.infrastructure.database import Base as PaymentsBase
from payments.infrastructure.models import OutboxEventRecord as PaymentsOutboxRecord
from service_common.messaging import RabbitEventPublisher, publish_pending_once
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def test_event_contracts_are_valid_json_schema_2020_12() -> None:
    from pathlib import Path

    event_schema_directory = Path(__file__).parents[1] / "contracts" / "events"
    for schema_path in event_schema_directory.glob("*.schema.json"):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    contract_names = {
        path.name.removesuffix(".v1.schema.json")
        for path in event_schema_directory.glob("*.v1.schema.json")
    }
    assert contract_names == {
        "OrderPlaced",
        "PaymentConfirmed",
        "OrderPaid",
        "OrderShipped",
        "OrderDelivered",
    }


class CapturingExchange:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, message: object, routing_key: str, mandatory: bool) -> None:
        assert mandatory is True
        assert routing_key.endswith(".v1")
        assert message.delivery_mode.value == 2
        self.events.append(json.loads(message.body))


@pytest.fixture
def sqlite_sessions() -> list[sessionmaker[Session]]:
    engines = [
        create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        for _ in range(2)
    ]
    OrdersBase.metadata.create_all(engines[0])
    PaymentsBase.metadata.create_all(engines[1])
    yield [sessionmaker(bind=engine, expire_on_commit=False) for engine in engines]
    for engine in engines:
        engine.dispose()


def test_payment_outbox_event_is_published_and_consumed_idempotently(
    sqlite_sessions: list[sessionmaker[Session]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import orders.application.event_handlers as order_events
    import payments.api.router as payment_router

    order_sessions, payment_sessions = sqlite_sessions
    order_id, reservation_id = uuid4(), uuid4()
    with order_sessions() as session:
        session.add(
            OrderRecord(
                id=order_id,
                status="PENDING_PAYMENT",
                total_amount=Decimal("30.00"),
                currency="USD",
            )
        )
        session.flush()
        session.add(
            CheckoutRequestRecord(
                idempotency_key="event-checkout",
                fingerprint="f" * 64,
                cart_id=uuid4(),
                order_id=order_id,
                shipping_address={"country": "US"},
                reservation_id=reservation_id,
            )
        )
        session.commit()

    monkeypatch.setattr(payment_router, "_order_total", lambda requested: (Decimal("30.00"), "USD"))
    with payment_sessions() as session:
        payment = payment_router.create_payment(
            payment_router.PaymentRequest(
                orderId=order_id,
                paymentMethodToken="mock-success",
            ),
            "payment-event-key",
            session,
        )
        assert payment.status == "CONFIRMED"

    payment_exchange = CapturingExchange()
    payment_publisher = RabbitEventPublisher(payment_exchange)
    assert asyncio.run(
        publish_pending_once(payment_sessions, PaymentsOutboxRecord, payment_publisher)
    )
    assert payment_exchange.events[0]["eventType"] == "PaymentConfirmed"
    event = payment_exchange.events[0]
    assert event["version"] == 1
    assert event["eventId"]
    assert event["data"]["orderId"] == str(order_id)
    correlation_id = str(uuid4())
    event["correlationId"] = correlation_id

    inventory_calls: list[str] = []

    class FakeInventoryClient:
        def commit(self, requested_reservation: object) -> dict[str, str]:
            assert requested_reservation == reservation_id
            inventory_calls.append("commit")
            return {}

    monkeypatch.setattr(order_events, "InventoryClient", FakeInventoryClient)
    order_events.consume_order_event(event, sessions=order_sessions)
    order_events.consume_order_event(event, sessions=order_sessions)

    with order_sessions() as session:
        order = session.get(OrderRecord, order_id)
        assert order is not None and order.status == "PAID"
        inbox_receipt = session.get(InboxEventRecord, UUID(event["eventId"]))
        assert inbox_receipt is not None
        assert inbox_receipt.correlation_id == UUID(correlation_id)
        paid_events = list(
            session.scalars(
                select(OrdersOutboxRecord).where(OrdersOutboxRecord.event_type == "OrderPaid")
            )
        )
        assert len(paid_events) == 1
    assert inventory_calls == ["commit"]

    order_exchange = CapturingExchange()
    order_publisher = RabbitEventPublisher(order_exchange)
    assert asyncio.run(publish_pending_once(order_sessions, OrdersOutboxRecord, order_publisher))
    assert order_exchange.events[0]["eventType"] == "OrderPaid"
    assert order_exchange.events[0]["data"]["orderId"] == str(order_id)


def test_order_shipped_and_delivered_events_update_order_state(
    sqlite_sessions: list[sessionmaker[Session]],
) -> None:
    from orders.application.event_handlers import consume_order_event

    order_sessions, _ = sqlite_sessions
    order_id = uuid4()
    with order_sessions() as session:
        session.add(
            OrderRecord(
                id=order_id,
                status="PAID",
                total_amount=Decimal("30.00"),
                currency="USD",
            )
        )
        session.commit()

    shipped = {
        "eventId": str(uuid4()),
        "eventType": "OrderShipped",
        "version": 1,
        "occurredAt": datetime.now(UTC).isoformat(),
        "producer": "shipping",
        "data": {
            "orderId": str(order_id),
            "shipmentId": str(uuid4()),
            "shippedAt": datetime.now(UTC).isoformat(),
        },
    }
    delivered = {
        "eventId": str(uuid4()),
        "eventType": "OrderDelivered",
        "version": 1,
        "occurredAt": datetime.now(UTC).isoformat(),
        "producer": "shipping",
        "data": {
            "orderId": str(order_id),
            "shipmentId": str(uuid4()),
            "deliveredAt": datetime.now(UTC).isoformat(),
        },
    }
    consume_order_event(shipped, sessions=order_sessions)
    consume_order_event(delivered, sessions=order_sessions)
    with order_sessions() as session:
        assert session.get(OrderRecord, order_id).status == "DELIVERED"


def test_notifications_consumes_order_paid_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import notifications.application.event_handlers as notification_events
    from notifications.infrastructure.database import Base as NotificationsBase
    from notifications.infrastructure.models import NotificationEventRecord
    from service_common.events import new_event
    from service_common.logging import correlation_id_var

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    NotificationsBase.metadata.create_all(engine)
    notification_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(notification_events, "SessionLocal", notification_sessions)
    order_id = uuid4()
    correlation_id = str(uuid4())
    token = correlation_id_var.set(correlation_id)
    try:
        event = new_event(
            "OrderPaid",
            "orders",
            {
                "orderId": str(order_id),
                "paymentId": str(uuid4()),
                "total": {"amount": "30.00", "currency": "USD"},
            },
            correlation_id,
        )
    finally:
        correlation_id_var.reset(token)

    notification_events.consume_notification_event(event)
    notification_events.consume_notification_event(event)
    with notification_sessions() as session:
        receipt = session.get(NotificationEventRecord, UUID(event["eventId"]))
        assert receipt is not None
        assert receipt.order_id == order_id
        assert receipt.correlation_id == UUID(correlation_id)
        assert len(list(session.scalars(select(NotificationEventRecord)))) == 1
    engine.dispose()
