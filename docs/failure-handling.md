# ShopEasy failure-handling strategy

The design assumes processes, networks, the broker, and the payment provider can fail independently. Each context remains the authority for its own committed data. A timeout means the caller did not receive an answer; it does not prove the remote operation did not happen.

## Synchronous calls

| Dependency / failure | Caller behavior |
|---|---|
| Catalog lookup times out/unavailable during checkout | Fail checkout promptly with retryable `503/504`; do not guess the price or use stale data in the initial design. Retry with bounded backoff only within the request budget. |
| Inventory reservation times out | Treat outcome as unknown. Retry the same idempotency key to obtain the original reservation result; do not issue a new reservation blindly. If resolution exceeds the checkout budget, mark the attempt for reconciliation and compensate/release once its reservation ID is known. |
| Inventory explicitly reports insufficient stock | Return a stable conflict; do not create a payable order. |
| Payments attempt call times out | Treat as unknown, retry/query with the same idempotency key. Do not create another payment attempt under a new key. Keep the order pending until resolved or policy expires it. |
| Payment provider unavailable | Payments keeps attempt pending or marks a terminal failure only when it knows the provider outcome; retries use provider idempotency where available. Do not report confirmation based on a timeout. |
| RabbitMQ unavailable while publishing | Commit local business state and outbox together; retry publishing from outbox with backoff. Do not lose the event or roll back an already committed payment merely because the broker is down. |

Set explicit connection and response timeouts for every HTTP dependency and an overall checkout deadline. Leave time for cleanup/response within the caller deadline. Choose concrete timeout values from local measurements during implementation and document them in configuration; do not leave client-library defaults implicit.

## Circuit breaker and retries

Use bounded retry with exponential backoff and jitter for transient network errors, `429`, and selected `5xx` responses. Honor `Retry-After` when present. Do not retry validation errors, insufficient stock, or other stable `4xx` responses. All mutating retries reuse the same idempotency key. A circuit breaker opens after a configured sequence/rate of dependency failures, fails fast while open, and probes recovery after a cool-down. It is per dependency and should not turn an unknown payment result into a failure. Record breaker state and retry counts for diagnosis.

## Checkout lifecycle and compensation

Checkout spans Orders, Inventory, Payments, and asynchronous events. It is a saga with local transactions, not a distributed ACID transaction:

1. Orders obtains current Catalog data and asks Inventory to reserve. Inventory commits an idempotent reservation and responds.
2. Orders persists `PENDING_PAYMENT` plus its outbox event, then requests a payment attempt with a stable key. If an order cannot be durably created, Orders releases the reservation.
3. Payments commits provider outcome and outbox event. Orders consumes `PaymentConfirmed` or terminal `PaymentFailed` idempotently.
4. A payment failure, expiry, or unrecoverable processing condition follows one explicit policy: allow a bounded retry while reservation remains valid, or cancel the order and idempotently release inventory. Do not hold stock indefinitely.
5. A late `PaymentConfirmed` for a cancelled order, mismatched amount, or unknown order enters a reconciliation path/alert. Do not silently mark it paid. Define whether to refund or contact an operator after choosing a provider and refund policy.

Inventory release and payment cancellation/refund are compensating actions, not database rollback. They must be safe to retry and have durable outcomes. Add a periodic reconciliation mechanism only when the initial failure modes are understood; first ensure each unknown outcome is persisted and observable.

## Messaging and handler safety

- RabbitMQ publishers write an outbox record in the same local transaction as the state change. The relay uses persistent messages and publisher confirms, then marks the row published. If it crashes after broker confirmation but before the database update, the event can be published again.
- RabbitMQ consumers use manual acknowledgement after commit, durable quorum queues, bounded redelivery, and a dead-letter queue.
- Persist an inbox/processed-event ID in the consumer's database in the same transaction as the state change. Duplicates become no-ops.
- Use a dead-letter queue after bounded attempts. Capture event ID, consumer, error category, and correlation ID; avoid secrets and full payment data in logs.
- Fix the underlying issue before replaying a DLQ message. Replay must preserve event ID so deduplication remains effective; provide an explicit operator procedure in implementation.
- The outbox relay retries publishing with exponential delays (starting at one second and capped at five minutes), skips records whose retry time has not arrived, and exposes pending age/count. Alert on sustained growth. A published event may arrive twice.
- Consumers validate schema/version and required fields. Unknown optional fields are ignored; unsupported major versions go to quarantine/DLQ rather than crashing a hot queue forever.
- Consumers use durable retry queues with 1s/4s/16s delays for transient failures. Permanent schema errors and stable 4xx rejections go directly to a DLQ. The DLQ retains the original message and event ID plus safe failure metadata for operator inspection.

See [Phase 6 operational behavior](phase6-failure-handling.md) for the implemented retry queues, timeout, circuit breaker states, and local DLQ inspection procedure.

## Correlation, logging, and observability

Carry `X-Correlation-ID` through gateway, HTTP calls, outbox rows, and event envelope. Preserve an event ID and causation ID in structured logs. Log operation, context, status, duration, retry count, and stable error category. Never log payment method tokens, secrets, or unnecessary personal data. Track checkout outcomes, HTTP dependency latency/timeouts, breaker transitions, duplicate deliveries, consumer lag, DLQ count, outbox age, and notification delivery outcomes. Health checks should distinguish process liveness from ability to accept work.

## Error response and fallback policy

Return actionable stable error codes without leaking internals. For mandatory checkout dependencies, fail closed: never invent a price, claim stock is reserved without confirmation, or claim payment succeeded without a committed provider result. A product listing can be unavailable when Catalog is down; the initial design does not add a cache/fallback data store. Notifications are best effort from the customer's checkout perspective: retry delivery asynchronously and record terminal failure without changing order/payment state.
