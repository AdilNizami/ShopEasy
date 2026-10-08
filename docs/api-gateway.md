# Phase 7: API Gateway

## Single front door

The frontend sends ShopEasy API calls to `http://localhost:8000` in local
development. The gateway is the only application API port published on the
host. It routes paths to the owning FastAPI service over the private Compose
network. This gives browser clients one stable origin and one place for
cross-cutting request concerns. Service locations can change without requiring
the frontend to know internal hostnames or ports.

Browser development origins are configured with `GATEWAY_FRONTEND_ORIGINS`
(comma-separated; `http://localhost:3000` by default). The gateway allows the
bearer Authorization, correlation, content-type, and idempotency headers needed
by the frontend, and exposes the response correlation ID.

The gateway passes the HTTP method, path, query, request body, status, and
response body through. It forwards the `Idempotency-Key` and safe content
headers, removes hop-by-hop headers, and forwards an access token only after
validating it. Correlation IDs are created/validated by the common
middleware, included in request logs, forwarded as `X-Correlation-ID`, and
returned in responses and structured gateway errors.

| Public path | Owning service |
|---|---|
| `/v1/auth` | Auth |
| `/v1/products`, `/v1/categories` | Catalog |
| `/v1/carts`, `/v1/checkout`, `/v1/orders` | Orders |
| `/v1/payments` | Payments |
| `/v1/inventory/availability` | Inventory |

Inventory stock administration, reservation, commit, and release routes stay
internal. They are called by backend services and are not frontend APIs.
Notifications has no customer-facing API in this project.

## Authentication

The gateway permits registration/login without a token, allows product and
availability reads, and verifies signed bearer tokens for protected routes.
Catalog enforces operator authorization for catalog writes. Orders independently
validates tokens before applying user ownership filters.
See [authentication and authorization](authentication.md) for token issuance,
hashing, and resource ownership. Health liveness is unauthenticated for process
monitoring.

## Timeouts and errors

Gateway-to-service requests use a configurable 1 second connection timeout and
3 second overall/read timeout by default. An upstream timeout returns HTTP 504;
a connection or transport failure returns HTTP 503. Those errors use the same
`error` envelope and correlation ID as backend APIs. Normal service responses,
including their structured business errors and status codes, pass through.
The gateway does not automatically retry requests: repeating a mutation after
an uncertain timeout could duplicate work unless the original idempotency key
is reused and its outcome is resolved.

The gateway also serves an operator-only, read-only `/v1/internal/observability/*`
surface for the engineering dashboard. It checks the signed `operator` role,
probes private service readiness endpoints, forwards telemetry requests to the
owning services, and reads RabbitMQ management data. It does not access service
databases or provide queue mutation controls. See
[the dashboard guide](observability-dashboard.md).

## What belongs in the gateway

- Public path routing and a stable frontend origin.
- Bearer-token verification before protected routes; Auth owns credentials and token issuance.
- Correlation ID propagation, request logging, bounded upstream timeouts, and
  consistent errors for gateway failures.

## What does not belong in the gateway

- Cart, pricing, stock, payment, or order rules.
- Database connections or reads/writes to any service's data.
- Checkout orchestration, event publishing/consuming, or service-to-service
  calls that belong to bounded contexts.
- Account/password rules and user-owned order rules, which belong to Auth and Orders.
- Automatic mutation retries or response caching that could alter business
  semantics.

Keeping the gateway thin avoids a second place where business rules could
drift. The owning service remains authoritative and can evolve behind its
contract while the frontend depends on one versioned public API.
