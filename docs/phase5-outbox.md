# Phase 5: Transactional outbox

Payments and Orders publish events, so each stores outgoing event records in
its own `outbox_events` table. For example, Payments saves a confirmed payment
and its `PaymentConfirmed` row in one local database transaction. Orders does
the same for `OrderPlaced` and for `OrderPaid` together with the corresponding
order status change. There is no cross-service transaction or database access.

## Relay and record status

A background relay in each producer service selects pending rows, publishes a
persistent RabbitMQ message with mandatory routing and publisher confirmation,
then records `PUBLISHED`. Rows retain their stable `event_id`; the relay records
`attempts`, `last_attempt_at`, `next_attempt_at`, `last_error`, `created_at`,
`updated_at`, and `published_at`. If publishing fails, the row stays `PENDING`
with the failure details. The relay retries with exponential delays from one
second up to five minutes; other eligible events can proceed while one event
waits for its next attempt. Multiple relay workers use row locking with
`SKIP LOCKED` so they do not normally claim the same pending row at the same
time.

## Failure window and delivery guarantee

Without an outbox, a process could commit its business change and crash before
publishing the event; the fact would be lost to subscribers. Saving the event
row in the same local transaction removes that gap: after commit, the relay can
publish it later even if RabbitMQ was unavailable during the original request.

Delivery is **at least once**, not exactly once. RabbitMQ can accept and confirm
a message, then the process can crash before its database transaction commits
`PUBLISHED`. On restart the still-pending row is sent again. The same `eventId`
is sent each time. Consumers must therefore be idempotent and record processed
event IDs in their own database transaction alongside their state changes (the
inbox pattern). Duplicate messages are expected; exactly-once delivery across
a database and a broker is not claimed.

## Operational limit

This phase retries transient publish errors while the service is running and
retries pending rows after restart. It does not add a separate permanent-failure
state. A permanently
invalid event will remain pending and needs investigation; do not mark it
published to silence the relay. The startup bootstrap adds the Phase 5 columns
to existing Phase 4 PostgreSQL outbox tables. Larger schema changes should use
versioned migrations.
