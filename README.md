# ShopEasy backend foundation

The Next.js storefront is in [`frontend/`](frontend/README.md). Start the full
stack with `docker compose up --build` and open `http://localhost:3000`; the
browser calls the API only through the gateway at `http://localhost:8000`.
The frontend boundaries and its current API limitations are described in
[`docs/frontend.md`](docs/frontend.md).
The operator-only event dashboard and access configuration are described in
[`docs/observability-dashboard.md`](docs/observability-dashboard.md).

Six separate FastAPI services run locally: Catalog, Orders, Payments, Inventory, Notifications, and Auth. Each service owns its persistence boundary; a minimal Notifications consumer records received order facts without sending email or other external messages. `service_common` contains transport infrastructure, event schema validation, RabbitMQ plumbing, and token-verification helpers, but no service domain models.

## Run locally with Docker Compose

1. Copy `.env.example` to `.env`, set the local database/broker passwords, and generate `AUTH_JWT_SECRET` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Run `docker compose up --build`.
3. Point the frontend to `http://localhost:8000`. Check gateway liveness at `http://localhost:8000/health/live`.

The gateway is the only host-exposed ShopEasy API service. It forwards `/v1/auth` to Auth; `/v1/products` and `/v1/categories` to Catalog; `/v1/carts`, `/v1/checkout`, and `/v1/orders` to Orders; `/v1/payments` to Payments; and `/v1/inventory/availability` to Inventory. Internal service ports are not published to the host. PostgreSQL has no host port mapping; RabbitMQ management is exposed only for local operations. Compose creates separate databases and login roles; each service receives only its own connection URL. The sample credentials are for local development only.

The service APIs are mounted under `/v1`. The contract reference is [`contracts/openapi/shop-easy-v1.yaml`](contracts/openapi/shop-easy-v1.yaml). Catalog owns product/category details, Orders owns carts/orders, Inventory owns stock and reservations, and Payments owns payment attempts. Checkout uses direct API calls when it needs an immediate answer, then uses versioned RabbitMQ events for committed facts. See [`docs/phase3-business-functionality.md`](docs/phase3-business-functionality.md) and [`docs/phase4-event-integration.md`](docs/phase4-event-integration.md).

Register and log in through `/v1/auth/register` and `/v1/auth/login`; use the returned bearer access token for protected requests. Orders enforces cart and order ownership. Authentication details, secret configuration, and existing-volume database setup are described in [`docs/authentication.md`](docs/authentication.md). The gateway routing boundary is described in [`docs/api-gateway.md`](docs/api-gateway.md).

Tables are initialized from each service's own SQLAlchemy metadata at container start. Payments and Orders store transactional outbox rows; Orders and Notifications deduplicate consumed event IDs in their own databases. RabbitMQ publishing and consuming run as background tasks. The outbox delivery guarantee, duplicate-publication failure window, and current retry limits are described in [`docs/phase5-outbox.md`](docs/phase5-outbox.md). Consumer retries, DLQ visibility, timeouts, and circuit-breaker behavior are described in [`docs/phase6-failure-handling.md`](docs/phase6-failure-handling.md). RabbitMQ management is available locally on port 15672. The small startup ALTER statements support the Phase 4 to Phase 5 local upgrade; introduce independently owned versioned migrations before evolving deployed databases.

## Local Python checks

With Python 3.12 installed, create a virtual environment and install `requirements-dev.txt`, then run `ruff check .`, `ruff format --check .`, and `pytest`. Domain tests cover cart totals/quantity, stock availability, order transitions, and mock outcomes. API/database integration tests can use SQLite; production service configuration uses PostgreSQL.
