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
from service_common.messaging import run_outbox_relay

from payments.api.router import router
from payments.infrastructure.config import settings
from payments.infrastructure.database import SessionLocal
from payments.infrastructure.models import OutboxEventRecord
from service_common.identity import Principal, require_operator

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not settings.messaging_enabled:
        yield
        return
    task = asyncio.create_task(
        run_outbox_relay(SessionLocal, OutboxEventRecord, settings.rabbitmq_url, "payments")
    )
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="ShopEasy Payments", version="1.0.0", lifespan=lifespan)
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
        return {
            "service": "payments",
            "outboxPendingCount": pending_count,
            "outboxFailureCount": failed_publish_count,
            "eventsProcessedCount": 0,
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
                    "lastError": event.last_error,
                }
                for event in outbox
            ],
            "processedEvents": [],
        }


app.include_router(router, prefix="/v1")
