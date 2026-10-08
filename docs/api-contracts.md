# ShopEasy API contracts

The machine-readable REST contract is [`contracts/openapi/shop-easy-v1.yaml`](../contracts/openapi/shop-easy-v1.yaml), OpenAPI 3.1. Its URL version is `/v1`; the server URL in the file is illustrative. It defines methods, paths, request and response schemas, validation constraints, and documented status/error responses. The Gateway routes public operations; operations marked `x-internal: true` are deliberately not routed through the public Gateway.

## Public Gateway route summary

| Method and path | Purpose | Access |
|---|---|---|
| `POST /v1/auth/register`, `POST /v1/auth/login` | Create an account or obtain an access token | Public |
| `GET /v1/auth/me` | Read identity and role from the access token | Authenticated |
| `GET /v1/products`, `GET /v1/products/{productId}` | Browse/search/filter products and read details | Public |
| `POST /v1/products` | Add a product | Operator |
| `GET /v1/categories`, `POST /v1/categories` | Browse categories or add one | Read public; write operator |
| `GET /v1/inventory/availability/{productId}` | Display current availability | Public; informational only |
| `POST /v1/carts`, `GET /v1/carts/{cartId}` | Create/read the caller's cart | Authenticated owner |
| `POST /v1/carts/{cartId}/items` | Add an item | Authenticated owner |
| `PUT /v1/carts/{cartId}/items/{productId}` | Set an absolute quantity atomically | Authenticated owner |
| `DELETE /v1/carts/{cartId}/items/{productId}` | Remove an item | Authenticated owner |
| `POST /v1/checkout` | Create or resume checkout; requires `Idempotency-Key` | Authenticated owner |
| `GET /v1/orders`, `GET /v1/orders/{orderId}`, `GET /v1/orders/{orderId}/status` | Read the caller's orders and status | Authenticated owner |
| `POST /v1/payments`, `GET /v1/payments/{paymentId}` | Create/read the caller's mock payment | Authenticated; requires `Idempotency-Key` on create |

The OpenAPI contract also lists internal Inventory operations for stock setup,
reservation, commit, and release. They are service-to-service/admin interfaces
and are not exposed as Gateway routes. The local demo guide explains how to
initialize stock through Inventory's own HTTP API without connecting to its
database.

## Errors and validation

Requests use camelCase JSON fields and reject invalid IDs, quantities, money,
and required values according to the schemas. Successful mutations document
their status codes in OpenAPI. Common failures include `400` for malformed
cursors, `401` for missing/invalid tokens, `403` for an authenticated customer
attempting an operator action, `404` for missing or non-owned resources, `409`
for business conflicts/idempotency-key reuse, `422` for invalid request data,
and `503`/`504` for unavailable/timed-out dependencies. Error responses use a
structured error body and correlation ID. Check the contract operation for
the exact response codes and schema rather than relying on this overview.

The API is an independent wire contract, not an implementation prescription. See [API versioning](api-versioning.md) and [backward compatibility](backward-compatibility.md) for evolution rules. Keep prices as decimal strings, treat cart prices as informational, and revalidate authoritative price at checkout. Checkout, payment, and inventory reservation use `Idempotency-Key`; cart quantity replacement uses an absolute `PUT`. Errors use a stable `error` object with a correlation ID and retryable flag.

Orders owns carts. Authentication uses the Auth context's `/v1/auth` endpoints and signed bearer access tokens. Orders filters carts and orders by the verified token subject; the Auth and Orders databases remain separate.
