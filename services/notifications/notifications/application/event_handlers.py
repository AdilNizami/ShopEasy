from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from service_common.events import validate_event

from notifications.infrastructure.database import SessionLocal
from notifications.infrastructure.models import NotificationEventRecord

SUBSCRIBED_EVENT_TYPES = {"OrderPlaced", "OrderPaid", "OrderShipped", "OrderDelivered"}


def consume_notification_event(event: dict[str, Any]) -> None:
    validate_event(event)
    event_type = event["eventType"]
    if event_type not in SUBSCRIBED_EVENT_TYPES:
        raise ValueError(f"Notifications does not consume {event_type}.")
    event_id = UUID(event["eventId"])
    order_id = UUID(event["data"]["orderId"])
    correlation_id = event.get("correlationId")
    with SessionLocal() as session:
        if session.get(NotificationEventRecord, event_id):
            return
        session.add(
            NotificationEventRecord(
                event_id=event_id,
                event_type=event_type,
                order_id=order_id,
                correlation_id=UUID(correlation_id) if correlation_id else None,
                received_at=datetime.now(UTC),
            )
        )
        session.commit()
