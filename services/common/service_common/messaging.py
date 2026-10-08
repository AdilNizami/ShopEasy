from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange
from fastapi import HTTPException
from jsonschema import ValidationError as EventSchemaValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from service_common.events import event_record_payload, validate_event
from service_common.logging import correlation_id_var

logger = logging.getLogger("shop_easy.messaging")
EVENT_EXCHANGE = "shopeasy.events"
DEAD_LETTER_EXCHANGE = "shopeasy.events.dlx"
RETRY_EXCHANGE = "shopeasy.events.retry"
RETRY_DELAYS_MS = (1_000, 4_000, 16_000)
RETRY_HEADER = "x-shop-easy-retry-count"


class RabbitEventPublisher:
    def __init__(self, exchange: AbstractExchange) -> None:
        self.exchange = exchange

    async def publish(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, separators=(",", ":")).encode()
        await self.exchange.publish(
            aio_pika.Message(
                body=payload,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=event["eventId"],
                correlation_id=event.get("correlationId"),
                type=f"{event['eventType']}.v{event['version']}",
                headers={"eventType": event["eventType"], "version": event["version"]},
            ),
            routing_key=f"{event['eventType']}.v{event['version']}",
            mandatory=True,
        )


def _next_outbox_record(session: Session, record_type: type) -> Any | None:
    return session.scalar(
        select(record_type)
        .where(record_type.status == "PENDING")
        .order_by(record_type.occurred_at, record_type.event_id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )


async def publish_pending_once(
    sessions: sessionmaker[Session], record_type: type, publisher: RabbitEventPublisher
) -> bool:
    with sessions() as session:
        record = _next_outbox_record(session, record_type)
        if record is None:
            return False
        event_id = record.event_id
        correlation_token = correlation_id_var.set(
            str(record.correlation_id) if record.correlation_id else "-"
        )
        try:
            try:
                await publisher.publish(event_record_payload(record))
            except Exception as exc:
                record.attempts += 1
                record.last_error = type(exc).__name__[:100]
                record.last_attempt_at = datetime.now(UTC)
                record.updated_at = datetime.now(UTC)
                session.commit()
                logger.exception(
                    "event publish failed event_id=%s event_type=%s",
                    event_id,
                    record.event_type,
                )
                raise
            record.attempts += 1
            record.last_attempt_at = datetime.now(UTC)
            record.updated_at = datetime.now(UTC)
            record.status = "PUBLISHED"
            record.published_at = datetime.now(UTC)
            record.last_error = None
            session.commit()
            logger.info("event published event_id=%s event_type=%s", event_id, record.event_type)
            return True
        finally:
            correlation_id_var.reset(correlation_token)


async def _relay_loop(
    sessions: sessionmaker[Session],
    record_type: type,
    rabbitmq_url: str,
    service_name: str,
) -> None:
    while True:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            async with connection:
                channel = await connection.channel(publisher_confirms=True)
                exchange = await channel.declare_exchange(
                    EVENT_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
                )
                publisher = RabbitEventPublisher(exchange)
                while True:
                    if not await publish_pending_once(sessions, record_type, publisher):
                        await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("event outbox relay disconnected service=%s", service_name)
            await asyncio.sleep(2)


async def _consume_loop(
    rabbitmq_url: str,
    queue_name: str,
    event_types: tuple[str, ...],
    handler: Callable[[dict[str, Any]], None],
) -> None:
    while True:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            async with connection:
                channel: AbstractChannel = await connection.channel(publisher_confirms=True)
                await channel.set_qos(prefetch_count=10)
                exchange = await channel.declare_exchange(
                    EVENT_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
                )
                dead_letter_exchange = await channel.declare_exchange(
                    DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
                )
                dead_letter_queue = await channel.declare_queue(f"{queue_name}.dlq", durable=True)
                await dead_letter_queue.bind(dead_letter_exchange, routing_key=queue_name)
                retry_exchange = await channel.declare_exchange(
                    RETRY_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
                )
                queue = await channel.declare_queue(
                    queue_name,
                    durable=True,
                    arguments={
                        "x-queue-type": "quorum",
                        "x-delivery-limit": 5,
                        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                        "x-dead-letter-routing-key": queue_name,
                    },
                )
                for event_type in event_types:
                    event_routing_key = f"{event_type}.v1"
                    await queue.bind(exchange, routing_key=event_routing_key)
                    for retry_number, delay_ms in enumerate(RETRY_DELAYS_MS, start=1):
                        retry_route = _retry_routing_key(
                            queue_name, event_routing_key, retry_number
                        )
                        retry_queue = await channel.declare_queue(
                            retry_route,
                            durable=True,
                            arguments={
                                "x-queue-type": "quorum",
                                "x-message-ttl": delay_ms,
                                "x-dead-letter-exchange": EVENT_EXCHANGE,
                                "x-dead-letter-routing-key": event_routing_key,
                                "x-dead-letter-strategy": "at-least-once",
                                "x-overflow": "reject-publish",
                            },
                        )
                        await retry_queue.bind(retry_exchange, routing_key=retry_route)

                async with queue.iterator() as iterator:
                    async for message in iterator:
                        await process_event_delivery(
                            message,
                            handler,
                            queue_name,
                            retry_exchange,
                            dead_letter_exchange,
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("event consumer disconnected queue=%s", queue_name)
            await asyncio.sleep(2)


async def run_outbox_relay(
    sessions: sessionmaker[Session], record_type: type, rabbitmq_url: str, service_name: str
) -> None:
    await _relay_loop(sessions, record_type, rabbitmq_url, service_name)


async def run_event_consumer(
    rabbitmq_url: str,
    queue_name: str,
    event_types: tuple[str, ...],
    handler: Callable[[dict[str, Any]], None],
) -> None:
    await _consume_loop(rabbitmq_url, queue_name, event_types, handler)


def _retry_routing_key(queue_name: str, event_routing_key: str, retry_number: int) -> str:
    return f"{queue_name}.{event_routing_key}.retry.{retry_number}"


def _is_permanent_failure(error: Exception) -> bool:
    if isinstance(
        error, (json.JSONDecodeError, EventSchemaValidationError, ValueError, TypeError, KeyError)
    ):
        return True
    if isinstance(error, HTTPException):
        return 400 <= error.status_code < 500 and error.status_code not in {408, 429}
    return False


async def process_event_delivery(
    message: Any,
    handler: Callable[[dict[str, Any]], None],
    queue_name: str,
    retry_exchange: Any,
    dead_letter_exchange: Any,
) -> None:
    """Handle one delivery; acknowledge only after commit or confirmed reroute."""
    try:
        event = json.loads(message.body)
        if not isinstance(event, dict):
            raise ValueError("Event envelope must be a JSON object.")
        validate_event(event)
        correlation_token = correlation_id_var.set(event.get("correlationId", "-"))
        try:
            await asyncio.to_thread(handler, event)
        finally:
            correlation_id_var.reset(correlation_token)
    except Exception as exc:
        headers = dict(getattr(message, "headers", None) or {})
        invalid_retry_count = False
        try:
            retry_count = int(headers.get(RETRY_HEADER, 0))
            if retry_count < 0:
                raise ValueError("Retry count cannot be negative.")
        except (TypeError, ValueError):
            # Bad broker metadata must not escape the error path and redeliver a
            # poison message forever. Route it to the DLQ with diagnostic context.
            retry_count = len(RETRY_DELAYS_MS)
            invalid_retry_count = True
        event_id = event.get("eventId") if "event" in locals() and isinstance(event, dict) else None
        correlation_id = (
            event.get("correlationId") if "event" in locals() and isinstance(event, dict) else None
        )
        original_routing_key = getattr(message, "routing_key", "") or "unknown"
        failure_headers = {
            **headers,
            "x-original-routing-key": original_routing_key,
            "x-failure-category": (
                "InvalidRetryCount" if invalid_retry_count else type(exc).__name__[:100]
            ),
            "x-failure-message": (
                "Permanent validation or business-rule failure."
                if _is_permanent_failure(exc)
                else "Transient consumer or downstream dependency failure."
            ),
            "x-failed-at": datetime.now(UTC).isoformat(),
        }
        failure_headers["x-event-id"] = str(event_id or getattr(message, "message_id", "unknown"))
        failure_headers["x-correlation-id"] = str(
            correlation_id or getattr(message, "correlation_id", "")
        )

        try:
            if invalid_retry_count or _is_permanent_failure(exc) or retry_count >= len(RETRY_DELAYS_MS):
                await dead_letter_exchange.publish(
                    _copy_message(message, failure_headers),
                    routing_key=queue_name,
                    mandatory=True,
                )
                logger.error(
                    "event sent to DLQ queue=%s event_id=%s retry_count=%d category=%s correlation_id=%s",
                    queue_name,
                    failure_headers["x-event-id"],
                    retry_count,
                    type(exc).__name__,
                    correlation_id or "-",
                )
            else:
                next_retry = retry_count + 1
                failure_headers[RETRY_HEADER] = next_retry
                event_routing_key = original_routing_key
                retry_route = _retry_routing_key(queue_name, event_routing_key, next_retry)
                await retry_exchange.publish(
                    _copy_message(message, failure_headers),
                    routing_key=retry_route,
                    mandatory=True,
                )
                logger.warning(
                    "event scheduled for retry queue=%s event_id=%s attempt=%d category=%s correlation_id=%s",
                    queue_name,
                    failure_headers["x-event-id"],
                    next_retry,
                    type(exc).__name__,
                    correlation_id or "-",
                )
        except Exception:
            logger.exception(
                "event failure could not be routed queue=%s event_id=%s",
                queue_name,
                failure_headers["x-event-id"],
            )
            await message.nack(requeue=True)
        else:
            await message.ack()
    else:
        await message.ack()


def _copy_message(message: Any, headers: dict[str, Any]) -> aio_pika.Message:
    return aio_pika.Message(
        body=message.body,
        headers=headers,
        content_type=getattr(message, "content_type", "application/json"),
        content_encoding=getattr(message, "content_encoding", None),
        delivery_mode=getattr(message, "delivery_mode", aio_pika.DeliveryMode.PERSISTENT),
        message_id=getattr(message, "message_id", None),
        correlation_id=getattr(message, "correlation_id", None),
        type=getattr(message, "type", None),
    )
