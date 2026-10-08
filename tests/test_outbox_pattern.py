import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from payments.infrastructure.database import Base
from payments.infrastructure.models import OutboxEventRecord, PaymentRecord
from service_common.messaging import publish_pending_once
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


class ScriptedPublisher:
    def __init__(self, outcomes: list[str] | None = None) -> None:
        self.outcomes = outcomes or []
        self.published: list[dict[str, Any]] = []

    async def publish(self, event: dict[str, Any]) -> None:
        outcome = self.outcomes.pop(0) if self.outcomes else "success"
        if outcome == "unavailable":
            raise ConnectionError("RabbitMQ is unavailable")
        self.published.append(event)


@pytest.fixture
def payment_sessions() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    yield sessions
    engine.dispose()


def create_confirmed_payment(
    monkeypatch: pytest.MonkeyPatch, sessions: sessionmaker[Session]
) -> None:
    import payments.api.router as payment_router

    order_id = uuid4()
    monkeypatch.setattr(
        payment_router,
        "_order_total",
        lambda requested_id: (Decimal("15.25"), "USD"),
    )
    with sessions() as session:
        response = payment_router.create_payment(
            payment_router.PaymentRequest(
                orderId=order_id,
                paymentMethodToken="mock-success",
            ),
            f"payment-{order_id}",
            session,
        )
        assert response.status == "CONFIRMED"


def test_business_commit_and_successful_publish_mark_outbox_published(
    payment_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_confirmed_payment(monkeypatch, payment_sessions)
    publisher = ScriptedPublisher()

    assert asyncio.run(publish_pending_once(payment_sessions, OutboxEventRecord, publisher)) is True

    with payment_sessions() as session:
        assert session.scalar(select(func.count()).select_from(PaymentRecord)) == 1
        record = session.scalar(select(OutboxEventRecord))
        assert record is not None
        assert record.status == "PUBLISHED"
        assert record.published_at is not None
        assert record.last_attempt_at is not None
        assert record.next_attempt_at is None
        assert record.attempts == 1
        assert record.last_error is None
        assert publisher.published[0]["eventId"] == str(record.event_id)


def test_broker_outage_does_not_lose_committed_business_state(
    payment_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_confirmed_payment(monkeypatch, payment_sessions)
    publisher = ScriptedPublisher(["unavailable"])

    with pytest.raises(ConnectionError):
        asyncio.run(publish_pending_once(payment_sessions, OutboxEventRecord, publisher))

    with payment_sessions() as session:
        assert session.scalar(select(func.count()).select_from(PaymentRecord)) == 1
        record = session.scalar(select(OutboxEventRecord))
        assert record is not None
        assert record.status == "PENDING"
        assert record.published_at is None
        assert record.attempts == 1
        assert record.last_attempt_at is not None
        assert record.last_error == "ConnectionError"
        assert record.next_attempt_at is not None


def test_pending_outbox_retries_after_broker_recovers(
    payment_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_confirmed_payment(monkeypatch, payment_sessions)
    publisher = ScriptedPublisher(["unavailable", "success"])
    failed_at = datetime.now(UTC)

    with pytest.raises(ConnectionError):
        asyncio.run(
            publish_pending_once(payment_sessions, OutboxEventRecord, publisher, now=failed_at)
        )
    assert (
        asyncio.run(
            publish_pending_once(
                payment_sessions,
                OutboxEventRecord,
                publisher,
                now=failed_at + timedelta(milliseconds=999),
            )
        )
        is False
    )
    assert asyncio.run(
        publish_pending_once(
            payment_sessions,
            OutboxEventRecord,
            publisher,
            now=failed_at + timedelta(seconds=1),
        )
    ) is True

    with payment_sessions() as session:
        record = session.scalar(select(OutboxEventRecord))
        assert record is not None
        assert record.status == "PUBLISHED"
        assert record.attempts == 2
        assert record.last_error is None
        assert record.published_at is not None
        assert publisher.published[0]["eventId"] == str(record.event_id)


def test_outbox_backoff_grows_exponentially_without_blocking_the_relay(
    payment_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_confirmed_payment(monkeypatch, payment_sessions)
    publisher = ScriptedPublisher(["unavailable", "unavailable", "success"])
    first_attempt = datetime.now(UTC)

    with pytest.raises(ConnectionError):
        asyncio.run(
            publish_pending_once(payment_sessions, OutboxEventRecord, publisher, now=first_attempt)
        )
    with pytest.raises(ConnectionError):
        asyncio.run(
            publish_pending_once(
                payment_sessions,
                OutboxEventRecord,
                publisher,
                now=first_attempt + timedelta(seconds=1),
            )
        )
    assert asyncio.run(
        publish_pending_once(
            payment_sessions,
            OutboxEventRecord,
            publisher,
            now=first_attempt + timedelta(seconds=2),
        )
    ) is False
    assert asyncio.run(
        publish_pending_once(
            payment_sessions,
            OutboxEventRecord,
            publisher,
            now=first_attempt + timedelta(seconds=3),
        )
    ) is True

    with payment_sessions() as session:
        record = session.scalar(select(OutboxEventRecord))
        assert record is not None
        assert record.attempts == 3


def test_crash_after_broker_acceptance_can_duplicate_same_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fail_commit = {"next": False}

    class FailOnceSession(Session):
        def commit(self) -> None:
            if fail_commit["next"]:
                fail_commit["next"] = False
                raise RuntimeError("simulated crash before published marker commit")
            super().commit()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, class_=FailOnceSession, expire_on_commit=False)
    create_confirmed_payment(monkeypatch, sessions)
    publisher = ScriptedPublisher()

    fail_commit["next"] = True
    with pytest.raises(RuntimeError, match="simulated crash"):
        asyncio.run(publish_pending_once(sessions, OutboxEventRecord, publisher))
    assert len(publisher.published) == 1

    assert asyncio.run(publish_pending_once(sessions, OutboxEventRecord, publisher)) is True
    assert len(publisher.published) == 2
    assert publisher.published[0]["eventId"] == publisher.published[1]["eventId"]
    with sessions() as session:
        record = session.scalar(select(OutboxEventRecord))
        assert record is not None and record.status == "PUBLISHED"
    engine.dispose()
