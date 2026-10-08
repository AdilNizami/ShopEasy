# ShopEasy context map

## Boundary rules

Each bounded context owns its business rules, data model, database, and migrations. Other contexts use its published HTTP API or consume its published events; they never read its tables, reuse its ORM models, or write its data. A context may store an external identifier and a snapshot needed for its own work. Such a snapshot is not shared ownership.

## Context responsibilities

| Context | Responsibilities and authoritative data | Inbound interface | Outbound interactions |
|---|---|---|---|
| Auth | Own usernames and password hashes; issue access tokens. | `/v1/auth/register`, `/v1/auth/login`, `/v1/auth/me` | Gateway and Orders validate signed tokens; no shared user database access. |
| Catalog | Own product name, description, price, sellable state, categories, and image URLs. | `GET/POST /v1/products`, `GET /v1/products/{productId}`, `/v1/categories` | Orders looks up current product details through HTTP. |
| Orders | Own carts, checkout requests, orders, immutable line/price snapshots, order status, and user IDs that own its carts/orders. | `/v1/carts`, `/v1/checkout`, `/v1/orders` | Verifies bearer tokens locally; asks Catalog, Inventory, and Payments when an immediate answer is needed; publishes `OrderPlaced` and `OrderPaid`; consumes payment and shipping facts. |
| Inventory | Own on-hand stock, reservations, expiry/release, and reservation idempotency. | `/v1/inventory/availability`, `/stock`, `/reservations` | Returns availability and reservation outcomes to callers through HTTP. It does not subscribe to `OrderPlaced`, because checkout needs stock reservation synchronously. |
| Payments | Own payment attempts and payment idempotency. The current provider adapter is a deterministic local mock. | `/v1/payments` | Validates order amount through Orders' HTTP API; publishes `PaymentConfirmed` through its outbox after confirmation. |
| Notifications | Consume selected business facts, decide message content/destination from available event data, record attempts and outcomes. | RabbitMQ subscriptions; optional internal delivery status API for operations. | External notification delivery adapter. Never owns or changes order/payment truth. |

There is no separate Cart, Shipping, or Pricing context in the implementation. Orders owns carts, and customer details are captured as an order-owned checkout snapshot. Stock is read from Inventory through its availability endpoint; it is never copied into Catalog. Add a new context only when it has distinct rules and ownership that the existing boundaries cannot responsibly own.

## Relationship map

```text
Client -> Gateway -> Catalog                      (HTTP: public product/category reads)
Client -> Gateway -> Inventory                    (HTTP: public availability read)
Client -> Gateway -> Orders                       (HTTP: authenticated cart, checkout, and order APIs)
Client -> Gateway -> Auth                         (HTTP: registration/login; bearer-token identity)
Gateway, Orders -> Auth token verifier             (local JWT verification; no user DB lookup)
Orders -> Catalog                                  (HTTP: current product/price)
Orders -> Inventory                                (HTTP: reserve then commit/release)
Orders -> Payments                                 (HTTP ASK: immediate mock payment outcome; Payments queries Orders API for order amount)
Payments -> RabbitMQ -> Orders                     (TELL: PaymentConfirmed)
Orders -> RabbitMQ -> downstream consumers         (TELL: OrderPlaced, OrderPaid)
Shipping -> RabbitMQ -> Orders                     (TELL: OrderShipped, OrderDelivered; producer outside this project)
```

`->` means a defined API or published message, not a database connection. Do not make every edge bidirectional. Consumers subscribe only to facts they need.

## Data ownership and consistency

Orders stores product IDs and the product name/price snapshot used for the order. This preserves what the customer agreed to even if Catalog later changes. Inventory owns the count and reservation state; Orders stores a reservation identifier and its outcome, not a copy of stock. Payments owns attempt/provider status; Orders stores payment attempt IDs and the outcome needed for order lifecycle. Notifications stores message/delivery state and the source event ID for deduplication.

There is no cross-database transaction. Each context commits its own state and outbox atomically. Inter-context operations are coordinated with synchronous answers where checkout needs a decision, and events for facts and downstream reactions. Compensation and reconciliation handle a multi-step checkout that cannot be made atomic.

## ASK vs TELL

- **ASK (HTTP request/response):** product details/current prices at checkout; reserve inventory; create a payment attempt; read an order. The caller needs an answer to continue or return a useful result.
- **TELL (event):** payment has been confirmed; an order has been placed/paid; a shipment has shipped/been delivered. The sender reports a committed fact and does not wait for every consumer.
- Do not publish a command as if it were a fact. `ReserveInventory` is a command/API request; `InventoryReserved` is a past-tense event emitted only after the reservation has committed.
- Do not use an event to fetch a current price or synchronously decide if stock can be reserved.
