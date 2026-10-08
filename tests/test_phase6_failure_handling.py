import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from orders.application.clients import ContextApiClient
from service_common.circuit_breaker import CircuitBreaker, CircuitOpenError
from service_common.events import new_event
from service_common.messaging import RETRY_HEADER, process_event_delivery
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class FakeIncomingMessage:
    def __init__(
        self,
        body: bytes,
        *,
        headers: dict[str, Any] | None = None,
        routing_key: str = "OrderPlaced.v1",
    ) -> None:
        self.body = body
        self.headers = headers or {}
        self.routing_key = routing_key
        self.message_id = "message-1"
        self.correlation_id = "correlation-1"
        self.content_type = "application/json"
        self.content_encoding = None
        self.delivery_mode = None
        self.type = "OrderPlaced.v1"
        self.acked = False
        self.nacked = False

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool = False) -> None:
        self.nacked = requeue


class FakeExchange:
    def __init__(self) -> None:
        self.publications: list[tuple[Any, str, bool]] = []

    async def publish(self, message: Any, routing_key: str, mandatory: bool) -> None:
        self.publications.append((message, routing_key, mandatory))


def valid_event() -> dict[str, Any]:
    return new_event(
        "OrderPlaced",
        "orders",
        {
            "orderId": str(uuid4()),
            "items": [
                {
                    "productId": str(uuid4()),
                    "name": "Example product",
                    "quantity": 1,
                    "unitPrice": {"amount": "12.50", "currency": "USD"},
                }
            ],
            "total": {"amount": "12.50", "currency": "USD"},
        },
        str(uuid4()),
    )


def test_duplicate_event_is_idempotent_in_consumer_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import notifications.application.event_handlers as handlers
    from notifications.infrastructure.database import Base
    from notifications.infrastructure.models import NotificationEventRecord

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(handlers, "SessionLocal", sessions)
    event = valid_event()

    handlers.consume_notification_event(event)
    handlers.consume_notification_event(event)

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(NotificationEventRecord)) == 1
    engine.dispose()


def test_transient_failure_is_scheduled_on_exponential_retry_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import service_common.messaging as messaging

    event = valid_event()
    message = FakeIncomingMessage(json.dumps(event).encode())
    retries, dead_letters = FakeExchange(), FakeExchange()
    logged_messages: list[str] = []
    monkeypatch.setattr(
        messaging.logger,
        "warning",
        lambda template, *args: logged_messages.append(template % args),
    )

    def fail_transiently(event: dict[str, Any]) -> None:
        raise RuntimeError("database temporarily unavailable")

    asyncio.run(
        process_event_delivery(message, fail_transiently, "orders.events.v1", retries, dead_letters)
    )

    assert message.acked
    assert not message.nacked
    assert len(retries.publications) == 1
    retried, route, mandatory = retries.publications[0]
    assert route.endswith(".retry.1")
    assert retried.headers[RETRY_HEADER] == 1
    assert retried.headers["x-failure-category"] == "RuntimeError"
    assert event["correlationId"] in logged_messages[0]
    assert mandatory
    assert not dead_letters.publications


def test_permanent_validation_failure_is_dead_lettered_without_retry() -> None:
    message = FakeIncomingMessage(b"not-json")
    retries, dead_letters = FakeExchange(), FakeExchange()

    asyncio.run(
        process_event_delivery(
            message, lambda event: None, "orders.events.v1", retries, dead_letters
        )
    )

    assert message.acked
    assert not retries.publications
    failed_message, route, mandatory = dead_letters.publications[0]
    assert route == "orders.events.v1"
    assert failed_message.headers["x-failure-category"] == "JSONDecodeError"
    assert failed_message.headers["x-event-id"] == "message-1"
    assert failed_message.headers["x-failed-at"]
    assert mandatory


def test_exhausted_retries_are_sent_to_dead_letter_queue() -> None:
    message = FakeIncomingMessage(json.dumps(valid_event()).encode(), headers={RETRY_HEADER: 3})
    retries, dead_letters = FakeExchange(), FakeExchange()

    def fail_transiently(event: dict[str, Any]) -> None:
        raise RuntimeError("dependency unavailable")

    asyncio.run(
        process_event_delivery(message, fail_transiently, "orders.events.v1", retries, dead_letters)
    )

    assert message.acked
    assert not retries.publications
    assert dead_letters.publications[0][1] == "orders.events.v1"


def test_invalid_retry_metadata_is_dead_lettered_instead_of_requeued() -> None:
    message = FakeIncomingMessage(
        json.dumps(valid_event()).encode(), headers={RETRY_HEADER: "not-a-number"}
    )
    retries, dead_letters = FakeExchange(), FakeExchange()

    def fail_transiently(event: dict[str, Any]) -> None:
        raise RuntimeError("dependency unavailable")

    asyncio.run(
        process_event_delivery(
            message, fail_transiently, "orders.events.v1", retries, dead_letters
        )
    )

    assert message.acked
    assert not message.nacked
    assert not retries.publications
    failed_message, _, mandatory = dead_letters.publications[0]
    assert mandatory
    assert failed_message.headers["x-failure-category"] == "InvalidRetryCount"


def test_http_timeout_is_bounded_and_returns_retryable_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_timeout: list[float] = []

    class TimeoutClient:
        def __init__(self, timeout: float) -> None:
            received_timeout.append(timeout)

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def request(self, *args: object, **kwargs: object) -> None:
            raise httpx.ReadTimeout("request timed out")

    monkeypatch.setattr(httpx, "Client", TimeoutClient)
    breaker = CircuitBreaker()
    client = ContextApiClient("http://catalog", breaker=breaker)

    with pytest.raises(HTTPException) as error:
        client.request("GET", "/v1/products")

    from orders.infrastructure.config import settings

    assert error.value.status_code == 503
    assert received_timeout == [settings.downstream_timeout_seconds]


def test_circuit_breaker_opens_and_allows_half_open_recovery_probe() -> None:
    now = [100.0]
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=5, clock=lambda: now[0])

    for _ in range(2):
        with pytest.raises(ConnectionError):
            breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("offline")))
    assert breaker.state == "OPEN"
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "must not run")

    now[0] += 5
    assert breaker.state == "HALF-OPEN"
    assert breaker.call(lambda: "recovered") == "recovered"
    assert breaker.state == "CLOSED"
