# Backend service foundation (Phase 2 snapshot)

This document records the initial Phase 2 scaffold. Phase 3 and Phase 4 extended these schemas and implemented checkout and RabbitMQ integration; see the current [README](../README.md) and [Phase 4 notes](phase4-event-integration.md).

## Services and data boundaries

| Service | Database | Owned tables | Service API |
|---|---|---|---|
| Catalog | `catalog` | `products` | Product list and detail reads. |
| Orders | `orders` | `orders`, `order_lines` | Checkout request validation and order/status reads. |
| Payments | `payments` | `payment_attempts` | Payment request validation and payment status reads. |
| Inventory | `inventory` | `stock`, `reservations`, `reservation_items` | Reservation request validation. |

Compose uses one PostgreSQL server for local convenience but creates four databases and four restricted login roles. Each service has its own SQLAlchemy `DeclarativeBase`, models, engine, session factory, settings, and repository boundary. IDs that refer to another context are plain UUID values: cross-context database foreign keys and direct reads are not used. Services do not import other service packages. `services/common/service_common` is limited to transport infrastructure such as correlation IDs, logging, error formatting, and settings.

## API behavior in this phase

Service routes use `/v1`, Pydantic request/response models, and the shapes in the OpenAPI contract where the service owns the endpoint. Catalog reads published products; Orders and Payments can read owned records. Checkout, payment creation, and Inventory reservation validate input but return a structured `503` until their required workflow integrations are implemented. They do not report successful checkout, payment, or stock reservation prematurely.

The cart API in the OpenAPI contract has no service among the four requested contexts. It remains a client-facing contract until its ownership/storage is decided. Authentication and caller-specific order filtering must be enforced by a future authenticated gateway/identity integration before these ports are exposed beyond local development.

## Cross-cutting behavior

- `GET /health/live` reports that the process responds.
- `GET /health/ready` checks that the service can connect to its own PostgreSQL database.
- `X-Correlation-ID` is accepted when it is a UUID; otherwise the service creates one. The value is returned in the response and included in JSON logs and structured errors.
- Pydantic validation failures use the stable `error` envelope with HTTP 422. HTTP errors preserve their HTTP status. Database failures become retryable 503 responses; unexpected failures are logged and return a non-retryable 500 without stack details.
- `DATABASE_URL`, `SERVICE_NAME`, and `LOG_LEVEL` are environment settings. The URL is validated as PostgreSQL.

## Local schema bootstrap limitation

Each container calls `Base.metadata.create_all` for its own model metadata before serving. This keeps the local foundation runnable and does not merge schemas. It does not handle migrations, destructive changes, or production rollout safety; add per-context migration histories before changing a deployed schema. Broker integration and domain workflows are intentionally absent in this phase.
