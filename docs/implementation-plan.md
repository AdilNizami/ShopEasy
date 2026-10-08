# ShopEasy implementation plan

This plan turns the proposed contracts into a small working system in reviewable steps. Stop after architecture/plan approval before beginning implementation. Do not add features outside the learning flow without a concrete need.

## Proposed repository structure

```text
.
├── apps/
│   └── web/                         # Next.js + TypeScript + Tailwind
├── services/
│   ├── catalog/                     # FastAPI app, own persistence/migrations
│   ├── orders/
│   ├── payments/
│   ├── inventory/
│   └── notifications/
├── packages/
│   └── contracts/                   # OpenAPI/JSON Schema and generated/client types only
├── docs/                            # Architecture decisions and contracts
├── compose.yaml                     # Local PostgreSQL, RabbitMQ, and app services
└── README.md
```

Each service owns its code, domain models, migrations, and database adapter. The contracts package contains wire schemas and generated types, not shared domain logic, ORM entities, or a shared database client. Do not create a monorepo tool or extra infrastructure until ordinary workspace scripts are insufficient. In Compose, use separate context databases/credentials and expose only the web/gateway entry point to the host.

## Phases

### 0. Confirm contracts and decisions

Review this architecture, settle the payment provider/webhook model, currency, customer identity/access, notification delivery scope, and inventory expiry/reconciliation policy. Add machine-readable OpenAPI and event schemas. Establish compatibility rules and example payloads before implementing producers or consumers.

**Exit:** agreed v1 request, response, status, error, event, and idempotency contracts; no cross-context DB dependencies.

### 1. Local foundation

Create Compose services for PostgreSQL, RabbitMQ, web app, and context APIs as needed. Give each context a distinct DB and credential. Add configuration/secrets patterns, migrations per context, structured logging, correlation middleware, and liveness/readiness endpoints. Document one-command startup and local development.

**Exit:** processes start locally, migrations are context-owned, and no database credential can access another context's database.

### 2. Catalog and browsing

Implement Catalog product read contracts and minimal seed data; implement the Next.js product listing/detail experience using the gateway contract. Keep displayed availability distinct from stock authority. Avoid creating product administration unless needed to seed or demonstrate the flow.

**Exit:** browser can retrieve and render products through the public API path.

### 3. Inventory reservation API

Implement stock ownership, atomic reservation, expiry/release, reservation idempotency, and the synchronous internal API. Define concurrency-safe updates in Inventory's own database. Add outbox/inbox plumbing only for events actually published/consumed.

**Exit:** concurrent requests cannot reserve more than available stock; repeated reservation/release calls are safe.

### 4. Orders checkout with synchronous dependencies

Implement checkout input validation, Catalog lookup, Inventory reservation, immutable price snapshot, order persistence, idempotency-key storage, pending state, and order read API. Add compensation for failures after reservation. Persist `OrderPlaced` through the transactional outbox.

**Exit:** checkout does not trust client prices, and an order can be read consistently from Orders.

### 5. Payment attempts and outcome event

Implement Payments attempt/callback boundary behind a provider adapter. Use provider idempotency, authenticate callbacks, deduplicate provider notifications, commit payment state and outbox event atomically. Start with a clearly labeled local provider simulator only if needed for a reproducible demo; never confuse it with real capture.

**Exit:** `PaymentConfirmed` is emitted only after a committed confirmed payment, and duplicate callbacks do not duplicate effects.

### 6. Event consumption and notifications

Implement RabbitMQ topology, outbox relay, consumer inbox, `PaymentConfirmed`/`PaymentFailed` processing in Orders, order event publishing, and Notifications consumer/delivery records. Add bounded retries and DLQ handling. Keep notification outages out of checkout's critical path.

**Exit:** the full happy path reaches `PAID`; duplicate delivery is harmless; poison messages are inspectable.

### 7. Failure behavior and user experience

Implement configured HTTP timeouts, bounded retries, circuit breakers, pending/unknown outcome handling, reservation expiry, late-payment reconciliation visibility, and customer-facing pending/failure states. Add operational views only if necessary to demonstrate recovery; do not build a generic admin system.

**Exit:** each documented dependency and broker failure has a defined observable outcome and recovery action.

### 8. Verification and portfolio polish

Use Pytest for context/domain/API/consumer tests and contract compatibility checks; validate web flows and Compose startup. Add reproducible seed/demo instructions and an architecture walkthrough. Verify no context queries another database and no event is used for an immediate checkout answer.

**Exit:** a reviewer can run the demo, follow correlation IDs through a checkout, inspect an outbox/DLQ failure scenario, and understand context ownership.

## Architectural risks and mitigations

| Risk | Why it matters | Mitigation / decision needed |
|---|---|---|
| Synchronous checkout is coupled to Catalog, Inventory, and Payments availability | Any mandatory dependency timeout can interrupt checkout. | Keep calls bounded, idempotent, observable; fail clearly; do not mask unknown results. |
| Reservation/payment are a distributed workflow | Crash or timeout between steps can leave holds or ambiguous payment outcomes. | Persist saga state, compensate idempotently, expire holds, reconcile late/unknown results. |
| Duplicate/out-of-order events | RabbitMQ retries and callback retries are normal. | Stable event IDs, inbox, state transition guards, amount/order validation, DLQ. |
| Outbox relay/broker failure | Committed business changes may not reach subscribers immediately. | Transactional outbox, retries, lag monitoring, replay procedure. |
| Price changes between browse and checkout | Displayed price can be stale. | Orders re-reads Catalog at checkout and snapshots the accepted price; clearly display it before payment. |
| Inventory oversell under concurrent checkout | A read-then-write implementation can reserve the same stock twice. | Inventory owns an atomic reservation operation and database-level concurrency strategy. |
| Payment success after order cancellation | Late provider callbacks can contradict local lifecycle. | Preserve event, detect conflict, alert/reconcile/refund policy; never silently reopen. |
| User identity and authorization are unspecified | Order reads and customer data need access control. | Decide authentication and ownership model before exposing order endpoints beyond local demo. |
| Shared contracts can become a hidden shared model | Generated types are useful, shared business objects couple contexts. | Share only wire schemas/types; keep internal domain models local. |
| Too many services for a learning project | Operational overhead can eclipse architecture learning. | Keep scope to five contexts and requested stack; implement incrementally while retaining DB/API boundaries. |
| Notification privacy and delivery are underspecified | Events may carry sensitive customer data and delivery can fail. | Minimize payloads; choose channel and retention before real delivery; keep attempts outside core state. |
| Gateway implementation and network auth are open | A gateway is required conceptually but no product is chosen. | Keep it thin; choose the smallest suitable implementation during phase 0; do not add an unrequested gateway technology. |

## Completion boundary for this task

The current task ends with these architecture documents. No application code, dependencies, database schemas, Compose services, or runtime behavior are implemented by this plan.
