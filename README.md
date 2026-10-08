# ShopEasy

ShopEasy is a small online store built as a technical fellowship project. A
customer can browse products, keep a cart, check out using a mock payment, and
track an order. The main purpose is to demonstrate how backend services can
own separate business areas and cooperate through APIs and events.

**This is a local learning/demo application, not a real store.** Payments use a
deterministic mock provider. There is no card processing, email delivery, or
Shipping service. The catalog and inventory start empty and must be prepared
for a live checkout demo.

## Run the demo

1. Copy `.env.example` to `.env` and set a random `AUTH_JWT_SECRET` (at least
   32 bytes). See [environment and setup instructions](docs/setup.md).
2. Start everything from the repository root:

   ```powershell
   docker compose up --build
   ```

3. Prepare an operator account, product, and stock by following the
   [fellowship demo guide](docs/demo-guide.md).
4. Open the storefront at [http://localhost:3000](http://localhost:3000).

The API Gateway is at `http://localhost:8000`. The browser sends API requests
to this single entry point; it does not call the context services directly.

## How the architecture works

See the [architecture diagram](docs/architecture-diagram.md) and
[architecture overview](docs/architecture.md) for component and sequence
diagrams.

### Bounded contexts

Each bounded context is a service that owns its data and business rules:

| Service | Owns |
|---|---|
| **Auth** | Usernames, password hashes, and access-token issuance |
| **Catalog** | Product descriptions, prices, categories, image URLs, and sellable state |
| **Orders** | User-owned carts, checkout, order lines/price snapshots, and order status |
| **Payments** | Payment attempts and idempotency; the provider is currently a local mock |
| **Inventory** | On-hand stock and time-limited stock reservations |
| **Notifications** | Idempotent receipts for selected events; no email is sent |

There is no separate Cart or Shipping service. Orders owns carts. Shipment
events come from an external/future Shipping producer that is not implemented
in this repository. Read the full [context map](docs/context-map.md).

### ASK and TELL

**ASK** is a direct request when the caller needs an answer right away. During
checkout, Orders asks Catalog for the current price, Inventory to reserve stock,
and Payments for the mock payment outcome. Payments asks Orders to verify the
order and amount before accepting a payment attempt. These are HTTP calls
because checkout needs their answers to continue safely.

**TELL** is an event announcing that a fact has already happened. Once a
payment is confirmed and saved, Payments tells subscribers by publishing
`PaymentConfirmed`. Orders consumes it, marks the order `PAID`, and tells
subscribers with `OrderPaid`. Producers do not call event consumers and wait
for their responses. Event consumers work asynchronously. See the
[ASK/TELL interaction table](docs/phase4-event-integration.md).

### Where the technologies are used

- **Direct API calls:** The frontend calls the Gateway; the Gateway routes to
  the owning service. Orders calls Catalog, Inventory, and Payments when
  checkout needs an immediate answer. Payments calls Orders to validate an
  order. These calls use configured timeouts.
- **API Gateway:** `services/gateway` is the browser's single API front door.
  It forwards `/v1` requests, checks bearer tokens, propagates correlation IDs,
  and returns consistent timeout/upstream errors. It does not calculate
  prices, reserve stock, or own order rules.
- **Message queue:** RabbitMQ transports facts between independently running
  services. It lets a publisher finish without waiting for subscribers.
- **Pub/Sub events:** Payments and Orders publish to a durable topic exchange;
  Orders and Notifications have their own subscriptions. Events are past-tense
  facts such as `OrderPlaced` and `PaymentConfirmed`. See
  [event documentation](docs/event-contracts.md).

### Duplicates, Outbox, retries, and DLQ

RabbitMQ delivery is **at least once**, so a consumer can receive the same
event more than once. Orders and Notifications store processed event IDs in
their own databases in the same transaction as their business change. Seeing
the same ID again becomes a no-op. Delivery is not exactly once.

Payments and Orders use the **Transactional Outbox**. Each saves the business
change and an outgoing event record together in its own database transaction.
A background relay publishes the record and marks it published only after
RabbitMQ confirms publication. If the broker is down, the record stays pending
and retries with exponential delay. If a process crashes after the broker
accepted the event but before the published marker is saved, the relay can send
it again with the same event ID. Consumer idempotency handles that duplicate.
Outbox reduces event-loss risk; it does not eliminate duplicate delivery. More
detail is in the [Outbox guide](docs/phase5-outbox.md).

Transient consumer errors use delayed retries (1, 4, and 16 seconds, with
bounded attempts). Permanent validation/business errors go directly to a dead
letter queue (DLQ); exhausted transient failures go there after retries. The
DLQ keeps the message and safe failure metadata for investigation. The
engineering dashboard can inspect a small sample, but automated replay is not
implemented. See [failure handling](docs/phase6-failure-handling.md) and the
[failure demo scenarios](docs/demo-guide.md#failure-demonstration-broker-outage-and-outbox-recovery).

### How service boundaries are protected

Each service owns its database and its data rules. The local Compose stack
runs one PostgreSQL server but creates separate databases and logins for Auth,
Catalog, Orders, Payments, Inventory, and Notifications. A service gets only
its own database URL and credentials. Other services use an HTTP API or a
published event; they do not read or write its tables or import its private
domain classes. This keeps each service authoritative and prevents one
service's schema changes from silently breaking another.

The API contracts are versioned under `/v1`; order/cart reads are restricted
to the authenticated owner. Product/category writes and internal operational
views require the operator role. See [API contracts](docs/api-contracts.md),
[API versioning](docs/api-versioning.md), and
[authentication](docs/authentication.md).

## Project guides

- [Architecture diagram](docs/architecture-diagram.md)
- [Architecture and boundaries](docs/architecture.md)
- [Context map](docs/context-map.md)
- [API documentation and route summary](docs/api-contracts.md) · [OpenAPI 3.1 contract](contracts/openapi/shop-easy-v1.yaml)
- [Event documentation](docs/event-contracts.md) · [JSON Schemas](contracts/events/)
- [Local setup and environment variables](docs/setup.md)
- [Docker Compose instructions](docs/docker.md)
- [Test and contract-validation instructions](docs/testing.md)
- [Example customer journey and failure scenarios](docs/demo-guide.md)
- [Engineering dashboard guide](docs/observability-dashboard.md)
- [Final architecture review and remaining risks](docs/final-architecture-review.md)

## Test commands

With Python 3.12 and development requirements installed:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

For a frontend production build, run `npm install` and `npm run build` in
`frontend/`. The frontend currently has no separate automated test script.
Detailed setup and test scope are in [`docs/testing.md`](docs/testing.md).
