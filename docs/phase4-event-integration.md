# Phase 4: RabbitMQ event integration

## ASK and TELL interactions

| Interaction | Pattern | Reason |
|---|---|---|
| Orders asks Catalog for current product details and price | ASK: HTTP request/response | Checkout needs an authoritative price before it can create the order. |
| Orders asks Inventory to reserve stock | ASK: HTTP request/response | Checkout needs the immediate yes/no answer before it can take payment. |
| Orders asks Inventory to commit the reservation while handling `PaymentConfirmed` | ASK: HTTP request/response | Orders needs Inventory's committed answer before it can move the order to `PAID`. |
| Orders asks Payments to process the mock payment | ASK: HTTP request/response | The checkout response needs to know whether the mock provider confirmed or failed the attempt. This response does not update Orders to `PAID`. |
| Payments reports `PaymentConfirmed` | TELL: RabbitMQ event | This is a committed fact. Payments stores the fact and outbox row together, then publishes asynchronously without calling Orders. |
| Orders reports `OrderPlaced` and `OrderPaid` | TELL: RabbitMQ events | These are committed order facts. Orders does not synchronously call event subscribers. |
| Shipping reports `OrderShipped` and `OrderDelivered` | TELL: RabbitMQ events | These are committed shipment facts. Shipping is outside the current service set; Orders consumes them to update order status. |

## Delivery and persistence

- The topic exchange is `shopeasy.events`; routing keys use `{eventType}.v{version}` (for example, `PaymentConfirmed.v1`). Messages are persistent. The publisher uses RabbitMQ publisher confirms.
- Payments writes a `PaymentConfirmed` outbox row in the same database transaction as the confirmed payment. Failed mock attempts do not emit `PaymentConfirmed`.
- Orders writes `OrderPlaced` with the newly persisted order. Its consumer handles `PaymentConfirmed`, commits the Inventory reservation through Inventory's API, then writes the `PAID` state, inbox receipt, and `OrderPaid` outbox row in one Orders database transaction.
- Orders also consumes `OrderShipped` and `OrderDelivered` and updates its own status. The shipping producer must publish only after its shipment fact is committed.
- Notifications consumes `OrderPlaced`, `OrderPaid`, `OrderShipped`, and `OrderDelivered`, recording each event ID once in its own database. This demonstrates a downstream subscriber without adding email or external delivery behavior.
- Outbox relays retry after broker errors. A crash after publish but before marking the row published can cause a duplicate; consumers deduplicate by `eventId` in their own inbox database.
- Orders uses a durable quorum queue with a delivery limit and dead-letter queue for events it cannot process after repeated attempts. Invalid schema messages are rejected to the DLQ. Fix the cause before replaying a message.
- Correlation IDs are copied into event envelopes when available and placed in AMQP metadata. Event IDs are stable across redelivery. Envelope and event payloads are validated against the JSON Schemas in `contracts/events/` before publication and consumption.

## Timing and failure behavior

After a confirmed payment, checkout may return `PENDING_PAYMENT` while Orders processes `PaymentConfirmed`. The order becomes `PAID` only after Inventory confirms reservation commit and Orders commits the status change. Clients can poll `GET /v1/orders/{orderId}/status`. RabbitMQ downtime does not discard a committed payment or order: the outbox rows remain pending and relay when the broker recovers.

This phase does not add a Shipping bounded context, a real payment provider, or notification delivery. `OrderShipped` and `OrderDelivered` are validated consumer inputs from an external shipping producer. Inventory does not consume `OrderPlaced` to reserve stock; the synchronous reservation answer is required during checkout, and processing a later event would be too late and could duplicate the reservation.
