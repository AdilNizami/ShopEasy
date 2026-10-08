from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource


def schema_directory() -> Path:
    configured = os.getenv("EVENT_SCHEMA_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "contracts" / "events"


@lru_cache(maxsize=1)
def _schema_registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    directory = schema_directory()
    schemas = {
        path.name.removesuffix(".v1.schema.json"): json.loads(path.read_text(encoding="utf-8"))
        for path in directory.glob("*.v1.schema.json")
    }
    resources = [
        json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.schema.json")
    ]
    registry = Registry()
    for resource in resources:
        registry = registry.with_resource(resource["$id"], Resource.from_contents(resource))
    return registry, schemas


def validate_event(event: dict[str, Any]) -> None:
    event_type = event.get("eventType")
    if not isinstance(event_type, str):
        raise ValueError("Event is missing eventType.")
    registry, schemas = _schema_registry()
    schema = schemas.get(event_type)
    if schema is None:
        raise ValueError(f"No event schema is registered for {event_type}.")
    try:
        Draft202012Validator(
            schema,
            registry=registry,
            format_checker=FormatChecker(),
        ).validate(event)
    except ValidationError as exc:
        raise ValueError(f"Event does not match {event_type} v1 schema.") from exc


def new_event(
    event_type: str,
    producer: str,
    data: dict[str, Any],
    correlation_id: str | None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "eventId": str(uuid4()),
        "eventType": event_type,
        "version": 1,
        "occurredAt": datetime.now(UTC).isoformat(),
        "producer": producer,
        "data": data,
    }
    if correlation_id:
        try:
            event["correlationId"] = str(UUID(correlation_id))
        except ValueError:
            pass
    validate_event(event)
    return event


def event_record_payload(record: Any) -> dict[str, Any]:
    occurred_at = record.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    event: dict[str, Any] = {
        "eventId": str(record.event_id),
        "eventType": record.event_type,
        "version": record.version,
        "occurredAt": occurred_at.astimezone(UTC).isoformat(),
        "producer": record.producer,
        "data": record.data,
    }
    if record.correlation_id:
        event["correlationId"] = str(record.correlation_id)
    validate_event(event)
    return event


def event_record_fields(event: dict[str, Any]) -> dict[str, Any]:
    occurred_at = datetime.fromisoformat(event["occurredAt"].replace("Z", "+00:00"))
    correlation_id = event.get("correlationId")
    return {
        "event_id": UUID(event["eventId"]),
        "event_type": event["eventType"],
        "version": event["version"],
        "occurred_at": occurred_at,
        "producer": event["producer"],
        "data": event["data"],
        "correlation_id": UUID(correlation_id) if correlation_id else None,
    }
