# ShopEasy event contracts

The machine-readable event contracts are JSON Schema Draft 2020-12 files in [`contracts/events/`](../contracts/events/). The common [`event-envelope.schema.json`](../contracts/events/event-envelope.schema.json) requires `eventId`, `eventType`, `version`, `occurredAt`, `producer`, and `data`. `correlationId` is optional. Each named v1 event schema constrains its event name, producer, and required payload fields.

| Event | Producer identifier | Fact represented |
|---|---|---|
| `OrderPlaced` | `orders` | An order was created. |
| `PaymentConfirmed` | `payments` | A payment was confirmed. |
| `OrderPaid` | `orders` | The order reached paid status. |
| `OrderShipped` | `shipping` | The order shipment was shipped. |
| `OrderDelivered` | `shipping` | The order shipment was delivered. |

The envelope always has `eventId` (UUID), `eventType`, integer `version`,
`occurredAt` (date-time), `producer`, and a `data` object. `correlationId`
is optional. Money amounts are decimal strings with an uppercase three-letter
currency code. Event-specific required data is defined in each schema:

| Versioned schema | Required `data` fields |
|---|---|
| `OrderPlaced.v1` | `orderId`, `total`, and item snapshots (`productId`, `name`, `quantity`, `unitPrice`) |
| `PaymentConfirmed.v1` | `paymentId`, `orderId`, `amount` |
| `OrderPaid.v1` | `orderId`, `paymentId`, `total` |
| `OrderShipped.v1` | `orderId`, `shipmentId`, `shippedAt` |
| `OrderDelivered.v1` | `orderId`, `shipmentId`, `deliveredAt` |

The event names are past-tense facts. `shipping` is a producer identifier in the wire contract. ShopEasy currently has no Shipping service; an external shipping system is responsible for publishing shipment facts after its own state commits.

Phase 4 publishes `OrderPlaced` from Orders, `PaymentConfirmed` from Payments, and `OrderPaid` from Orders. Orders consumes `PaymentConfirmed`, `OrderShipped`, and `OrderDelivered`; Notifications subscribes to order and shipment facts and records them idempotently. Shipment events are external inputs because this project does not currently have a Shipping service. Publishing uses a durable RabbitMQ topic exchange and transactional outboxes; consumers deduplicate event IDs in their own databases. See [the Phase 4 interaction and failure notes](phase4-event-integration.md).

The v1 wire shape is a contract, not an ORM or database record. The producer
creates an immutable event ID for each committed fact. Outbox redelivery
preserves that ID. RabbitMQ is configured for at-least-once delivery; Orders
and Notifications store handled IDs in their own database transaction so a
duplicate is not applied twice. Consumers currently bind to v1 routing keys.

Consumers should expect duplicate and delayed delivery. Producers preserve `eventId` when redelivering. Consumers should ignore unknown optional fields and deduplicate by event ID. Breaking payload changes require a new major schema version and staged consumer migration; see [backward compatibility](backward-compatibility.md).
