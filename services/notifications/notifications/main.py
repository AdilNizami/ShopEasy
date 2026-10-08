import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import func, select

from service_common.http import (
    CorrelationIdMiddleware,
    install_error_handlers,
    install_health_routes,
)
from service_common.logging import configure_logging
from service_common.messaging import run_event_consumer

from notifications.application.event_handlers import (
    SUBSCRIBED_EVENT_TYPES,
    consume_notification_event,
)
from notifications.infrastructure.config import settings
from notifications.infrastructure.database import SessionLocal
from notifications.infrastructure.models import NotificationEventRecord
from service_common.identity import Principal, require_operator

configure_logging(settings.log_level)


def _event_producer(event_type: str) -> str:
    return "shipping" if event_type in {"OrderShipped", "OrderDelivered"} else "orders"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not settings.messaging_enabled:
        yield
        return
    task = asyncio.create_task(
        run_event_consumer(
            settings.rabbitmq_url,
            settings.event_queue_name,
            tuple(sorted(SUBSCRIBED_EVENT_TYPES)),
            consume_notification_event,
        )
    )
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="ShopEasy Notifications", version="1.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
install_error_handlers(app)
install_health_routes(app, settings.service_name, SessionLocal)


@app.get("/internal/observability", include_in_schema=False)
def observability_snapshot(
    _operator: Principal = Depends(require_operator),
) -> dict[str, object]:
    with SessionLocal() as session:
        records = session.scalars(
            select(NotificationEventRecord)
            .order_by(NotificationEventRecord.received_at.desc())
            .limit(100)
        ).all()
        processed_count = session.scalar(
            select(func.count()).select_from(NotificationEventRecord)
        ) or 0
        return {
            "service": "notifications",
            "outboxPendingCount": 0,
            "outboxFailureCount": 0,
            "eventsProcessedCount": processed_count,
            "outboxEvents": [],
            "processedEvents": [
                {
                    "eventId": str(event.event_id),
                    "eventType": event.event_type,
                    "producer": _event_producer(event.event_type),
                    "timestamp": event.received_at.isoformat(),
                    "correlationId": str(event.correlation_id) if event.correlation_id else None,
                    "processingStatus": "PROCESSED",
                    "retryCount": None,
                }
                for event in records
            ],
        }
