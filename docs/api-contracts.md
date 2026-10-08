# ShopEasy API contracts

The machine-readable REST contract is [`contracts/openapi/shop-easy-v1.yaml`](../contracts/openapi/shop-easy-v1.yaml), OpenAPI 3.1. Its URL version is `/v1`; its server URL is illustrative. It covers registration/login, product listing/details, cart access and mutation, checkout, order listing/details/status, payment request/status, and Inventory interfaces. Operations marked `x-internal: true` are service-to-service/admin APIs and are deliberately not routed by the public gateway. It defines methods, paths, request and response schemas, validation constraints, and documented status/error responses.

The API is an independent wire contract, not an implementation prescription. See [API versioning](api-versioning.md) and [backward compatibility](backward-compatibility.md) for evolution rules. Keep prices as decimal strings, treat cart prices as informational, and revalidate authoritative price at checkout. Checkout, payment, and inventory reservation use `Idempotency-Key`; cart quantity replacement uses an absolute `PUT`. Errors use a stable `error` object with a correlation ID and retryable flag.

Orders owns carts. Authentication uses the Auth context's `/v1/auth` endpoints and signed bearer access tokens. Orders filters carts and orders by the verified token subject; the Auth and Orders databases remain separate.
