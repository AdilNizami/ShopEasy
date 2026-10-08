# Phase 3: synchronous customer checkout

## Service boundaries

- **Catalog** owns product descriptions, prices, categories, and image URLs. It supports product creation for local/demo setup, listing/search/filter, and details. A product's `sellable` flag means it can be offered; it does not promise stock.
- **Inventory** owns on-hand counts and reservations. Clients read stock through `GET /v1/inventory/availability/{productId}`. Catalog does not copy stock into its product record, and no other service reads the Inventory database.
- **Orders** owns carts and orders. Adding an item asks Catalog for its current price and snapshots it in the cart. Checkout reads Catalog again and stores the accepted price on the order, so the browser never supplies a trusted price.
- **Payments** owns payment attempts and uses a deterministic mock provider. `mock-success` and `mock-failure` are demo selectors, not real payment credentials.

## Checkout sequence

1. The client creates a cart, adds products, and submits `POST /v1/checkout` with `cartId`, shipping address, mock token, and `Idempotency-Key`.
2. Orders re-reads each product from Catalog, validates sellability and currency, snapshots current prices, and persists a `PENDING_PAYMENT` order before contacting Payments. The order exists before Payments verifies its amount through the Orders API.
3. Orders asks Inventory to reserve the order's quantities. The reservation API is idempotent and has a bounded expiry.
4. Orders asks Payments to create an idempotent attempt. On `CONFIRMED`, Payments records a `PaymentConfirmed` event; Orders commits the reservation and changes the order to `PAID` when it consumes that event. On `FAILED`, Orders releases stock, marks the order `CANCELLED`, and reopens the cart.
5. A replay with the same idempotency key resumes the stored workflow. The same key with a different request returns `409`.

Catalog lookup, reservation, and mock payment outcome are ASK interactions over direct HTTP because checkout needs their immediate answers. `PaymentConfirmed` and `OrderPaid` are TELL events: they describe committed facts and are processed asynchronously. Checkout can initially return `PENDING_PAYMENT`; the client can poll order status while Orders processes the event. Calls use configured HTTP timeouts, pass the correlation ID, and do not cross database boundaries.

## Known limits in this learning phase

- The mock provider has no asynchronous callback, card handling, or real charge/refund behavior.
- A dependency timeout can leave an order `PENDING_PAYMENT`; retry checkout with the same key to resume. Inventory reservation expiry prevents indefinite holds. A production version needs explicit reconciliation for late/uncertain payment outcomes.
- This Phase 3 snapshot predates Phase 8 authentication. See [authentication and authorization](authentication.md) for current bearer-token and resource-ownership behavior.
- `create_all` is suitable only for this local learning setup. Introduce per-service migrations before evolving deployed schemas.
- Product stock display is a separate Inventory API request. A displayed quantity can change before checkout; reservation is the final availability decision.
