# ShopEasy architecture proposal

## Repository inspection

The repository is currently empty apart from `.git`: there is no application code, documentation, dependency manifest, or existing architecture to preserve. This proposal therefore establishes the initial design rather than describing an existing system. It uses only the requested stack: Next.js, TypeScript, Tailwind CSS, FastAPI, PostgreSQL, RabbitMQ, Docker Compose, and Pytest.

## Goals and scope

ShopEasy is a portfolio-scale, event-driven commerce application for learning contract-first design, service boundaries, synchronous APIs, asynchronous messaging, and failure handling. The first business flow is product browsing through successful payment and order confirmation. The architecture keeps each context responsible for its own data and rules, and makes cross-context communication explicit.

This is a proposal, not a commitment to deploy each context as an independently operated production service on day one. A context is an ownership boundary; it can initially run as a separate FastAPI application/container with its own PostgreSQL database. It must not be implemented as modules that query each other's tables. Avoid adding search engines, caches, Kubernetes, separate frontend services, or other technologies without a demonstrated requirement.

## Proposed shape

```text
Browser ──HTTPS──> Next.js web app ──HTTPS──> API Gateway
                                                │
                   ┌────────────────────────────┼─────────────────────────┐
                   │                            │                         │
                Catalog                      Orders                    Payments
                   │                            │                         │
                catalog DB                  orders DB                 payments DB
                                                │                         │
                                             Inventory <──HTTP──> Payment provider
                                                │
                                           inventory DB

                 Context publishers ──outbox relay──> RabbitMQ ──> context consumers
                                                        │
                                                   Notifications
                                                   notifications DB
```

The diagram shows logical ownership and calls, not a mandate to expose every container publicly. The gateway is the public API entry point and routes versioned requests to context APIs. Only the gateway should be exposed to the browser; internal context APIs and RabbitMQ should stay on the Compose network. The implementation uses a thin FastAPI gateway and an Auth service for user accounts; Orders verifies tokens and enforces ownership without reading Auth data.

## Context ownership and data

| Context | Owns | Does not own |
|---|---|---|
| Auth | Usernames, password hashes, and access-token issuance | Carts/orders or another context's records |
| Catalog | Product descriptions, display price, publication/visibility state | Stock counts, orders, payment status |
| Orders | Order identity, immutable checkout lines and price snapshots, lifecycle/status | Product master data, payment provider records, inventory quantities |
| Payments | Payment attempts, provider references, payment status and idempotency | Order lifecycle, inventory, product data |
| Inventory | Available/reserved quantities and reservation lifecycle | Order status, product descriptions, payment status |
| Notifications | Delivery records and notification outcomes | Order/payment truth or customer account management |

Each context owns its schema, migrations, credentials, and persistence interface. In a local Compose environment, use a distinct PostgreSQL database per context (or, if one PostgreSQL server is used for convenience, distinct databases and credentials). No context connects to another context's database. A shared server is not a shared database or permission to share tables. RabbitMQ is transport, not a source of business truth.

## Checkout and interaction choices

The browser cart is client-side presentation state in the initial scope; there is no Cart bounded context. At checkout, the client submits product IDs, quantities, a stable idempotency key, and a shipping/contact payload as needed. It does not submit authoritative prices. Orders obtains current product details and price from Catalog synchronously, then asks Inventory to reserve the requested quantities synchronously. Both answers are needed to decide whether checkout can proceed, so a request/reply API is appropriate here; an event cannot provide the immediate decision.

If validation and reservation succeed, Orders records a `PENDING_PAYMENT` order with price snapshots and requests a payment attempt synchronously from Payments. Payments returns an attempt/reference and a state such as `PENDING`; this means the payment request was accepted, not that money was captured. The customer-facing checkout response can return the pending order. Payment provider completion is asynchronous. Payments records the result and publishes `PaymentConfirmed` only after its local payment state has been durably committed. Orders consumes that event and marks the order `PAID`.

Orders is the checkout process coordinator because it owns the customer's order and must combine the synchronous answers. It is not allowed to update Inventory or Payments data directly. Each context uses local transactions; there is no distributed transaction. Inventory reservation is compensated by releasing it if order creation or payment initiation cannot proceed. A payment failure or timeout leads to a defined pending/retry or cancellation path and a reservation release; exact timeout policy and customer messaging belong to implementation. A late success after cancellation requires reconciliation and must never silently resurrect an order.

On order creation, Orders persists the order and its outgoing `OrderPlaced` record atomically via an outbox. Inventory may consume it for reconciliation/analytics, but must not treat a delayed event as the checkout reservation command: reservation was synchronously acknowledged. `PaymentConfirmed` and `PaymentFailed` are facts; Orders handles them idempotently. Notifications consumes relevant facts and records deliveries independently. It does not delay payment or order state changes.

## Contract-first and versioning

Define HTTP request/response shapes and event envelopes before implementation. The machine-readable REST contract is `contracts/openapi/shop-easy-v1.yaml`; event schemas are in `contracts/events/`. The gateway routes `/v1/...`; additive optional response fields and new event fields are preferred. Do not change the meaning or type of a published field in place. Introduce a new API or event major version for incompatible changes, support an overlap/migration period, and remove old versions only after consumers migrate. Unknown event fields should be ignored by consumers. No consumer should depend on another context's private database schema. See `docs/api-versioning.md` and `docs/backward-compatibility.md`.

## Operational baseline

Use correlation IDs across gateway requests, context calls, outbox records, and RabbitMQ messages. Propagate an incoming valid ID or create one at the gateway; include it in logs and error responses. Set explicit connect/read timeouts on internal HTTP and provider calls. Use bounded retries only for transient failures and only when the operation is idempotent. Apply a circuit breaker to repeated failures of remote dependencies so the system fails promptly and recovers rather than piling up requests. Keep secrets out of source control and logs. Health/readiness endpoints distinguish process liveness from dependency readiness.

## Initial decisions to revisit with evidence

1. Whether all context processes run as separate Compose services initially or some deployment packaging is combined while preserving independent data and interfaces.
2. Payment provider and its webhook/authentication behavior; the provider is an external dependency, not a new ShopEasy bounded context.
3. Reservation expiry and reconciliation policy, especially for payment timeouts and late callbacks.
4. The gateway/auth implementation is now a thin FastAPI gateway plus a dedicated Auth context; keep its user data isolated from Orders and enforce resource ownership inside Orders.
5. Whether customer notifications require email delivery in the first demo or can be shown as recorded delivery attempts.

## Phase 3 and Phase 4 implementation notes

Orders owns carts. Checkout asks Catalog for current product data, asks Inventory to reserve, and asks Payments to process the mock payment. A failed payment releases the reservation and cancels the order. A confirmed payment is published as `PaymentConfirmed`; Orders commits the reservation and changes the order to `PAID` asynchronously when it consumes that event. Orders writes `OrderPlaced` and `OrderPaid` to its outbox. `OrderShipped` and `OrderDelivered` are consumed from the external shipping producer defined by the existing contracts. Each cross-context interaction uses the owning service's API or a versioned event; there are no cross-context database reads or writes.
