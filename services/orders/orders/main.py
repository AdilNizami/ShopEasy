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
from service_common.messaging import run_event_consumer, run_outbox_relay

from orders.api.router import carts_router, checkout_router, orders_router
from orders.application.event_handlers import consume_order_event
from orders.infrastructure.config import settings
from orders.infrastructure.database import SessionLocal
from orders.infrastructure.models import InboxEventRecord, OutboxEventRecord
from service_common.identity import Principal, require_operator

configure_logging(settings.log_level)


def _event_producer(event_type: str) -> str:
    if event_type in {"OrderShipped", "OrderDelivered"}:
        return "shipping"
    if event_type == "PaymentConfirmed":
        return "payments"
    return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not settings.messaging_enabled:
        yield
        return
    tasks = [
        asyncio.create_task(
            run_outbox_relay(SessionLocal, OutboxEventRecord, settings.rabbitmq_url, "orders")
        ),
        asyncio.create_task(
            run_event_consumer(
                settings.rabbitmq_url,
                settings.event_queue_name,
                ("PaymentConfirmed", "OrderShipped", "OrderDelivered"),
                consume_order_event,
            )
        ),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="ShopEasy Orders", version="1.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
install_error_handlers(app)
install_health_routes(app, settings.service_name, SessionLocal)


@app.get("/internal/observability", include_in_schema=False)
def observability_snapshot(
    _operator: Principal = Depends(require_operator),
) -> dict[str, object]:
    with SessionLocal() as session:
        outbox = session.scalars(
            select(OutboxEventRecord).order_by(OutboxEventRecord.occurred_at.desc()).limit(100)
        ).all()
        processed = session.scalars(
            select(InboxEventRecord).order_by(InboxEventRecord.processed_at.desc()).limit(100)
        ).all()
        pending_count = session.scalar(
            select(func.count()).select_from(OutboxEventRecord).where(
                OutboxEventRecord.status == "PENDING"
            )
        ) or 0
        failed_publish_count = session.scalar(
            select(func.count())
            .select_from(OutboxEventRecord)
            .where(OutboxEventRecord.status == "PENDING", OutboxEventRecord.last_error.is_not(None))
        ) or 0
        processed_count = session.scalar(select(func.count()).select_from(InboxEventRecord)) or 0
        return {
            "service": "orders",
            "outboxPendingCount": pending_count,
            "outboxFailureCount": failed_publish_count,
            "eventsProcessedCount": processed_count,
            "outboxEvents": [
                {
                    "eventId": str(event.event_id),
                    "eventType": event.event_type,
                    "version": event.version,
                    "occurredAt": event.occurred_at.isoformat(),
                    "producer": event.producer,
                    "status": event.status,
                    "correlationId": str(event.correlation_id) if event.correlation_id else None,
                    "retryCount": event.attempts,
                    "lastAttemptAt": event.last_attempt_at.isoformat() if event.last_attempt_at else None,
                    "nextAttemptAt": event.next_attempt_at.isoformat() if event.next_attempt_at else None,
                    "lastError": event.last_error,
                }
                for event in outbox
            ],
            "processedEvents": [
                {
                    "eventId": str(event.event_id),
                    "eventType": event.event_type,
                    "producer": _event_producer(event.event_type),
                    "timestamp": event.processed_at.isoformat(),
                    "correlationId": (
                        str(event.correlation_id) if event.correlation_id else None
                    ),
                    "processingStatus": "PROCESSED",
                    "retryCount": None,
                }
                for event in processed
            ],
        }


app.include_router(carts_router, prefix="/v1")
app.include_router(checkout_router, prefix="/v1")
app.include_router(orders_router, prefix="/v1")
