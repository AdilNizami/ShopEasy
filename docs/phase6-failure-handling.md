# Phase 6: Production failure handling

## Event delivery and idempotency

Orders stores handled event IDs in its `inbox_events` table; Notifications stores
them as primary keys in `notification_events`. Each receipt is committed in the
same local transaction as its business change. A repeated event ID is a no-op.
Inventory commit is also idempotent, which matters because Orders must call its
API before it can commit the Inbox receipt; a crash in between can cause the
same commit request again.

Rabbit consumers acknowledge only after a handler commits, or after a retry/DLQ
copy has been publisher-confirmed. Transient failures are sent to durable
quorum retry queues with 1s, 4s, and 16s TTL delays. The retry count travels in
the message header. After three retries the message is routed to that
consumer's durable `.dlq` queue. JSON/schema validation errors and stable 4xx
business rejections go straight to the DLQ. The original message is requeued if
retry/DLQ publication itself fails, avoiding loss during a broker failure.

Failed messages keep their original event ID/body and include safe diagnostic
headers: consumer routing key, correlation ID, failure category, a general
failure summary, failure time, and retry count. RabbitMQ's management console
is exposed locally at `http://localhost:15672`; use the RabbitMQ credentials
from `.env` to inspect queue depth and DLQ messages. Logs include consumer,
event ID, retry count, and failure category. Do not replay until the cause is
fixed, and preserve event IDs during replay.

## HTTP timeout and circuit breaker

Synchronous context clients use the configured `DOWNSTREAM_TIMEOUT_SECONDS`
(2 seconds by default) rather than waiting indefinitely. Orders' Catalog,
Inventory, and Payments clients, plus Payments' Orders lookup, use an in-process
circuit breaker per downstream URL. Three consecutive network errors, 429s,
or 5xx responses open the circuit. Calls fail fast for 10 seconds; then one
request probes in HALF-OPEN. Success closes the circuit; failure opens it
again. State transitions are logged. A caller can retry a timed-out mutation
only with the same idempotency key; this phase does not hide uncertain outcomes
with automatic mutating retries.

## Fallback policy

Checkout fails closed when Catalog, Inventory, or Payments cannot answer. A
cached price, assumed reservation, or assumed payment result could charge the
customer incorrectly, so there is no fallback for those answers. Notifications
are asynchronous and do not sit on the checkout request path; their failures
are retried and then visible in their DLQ without changing order/payment state.

## Scope and limits

Retries are bounded and broker-backed, not an in-memory retry loop. DLQ messages
remain durable until an operator fixes and replays or removes them. The
management console is for local development; protect broker management access
with network policy and credentials in any deployed environment. There is no
exactly-once delivery claim: consumers rely on inbox IDs and idempotent
downstream operations.
