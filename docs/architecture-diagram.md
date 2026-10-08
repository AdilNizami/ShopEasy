# ShopEasy architecture diagrams

## Components and communication

```mermaid
flowchart TB
    Customer[Customer / operator] --> Browser[Next.js storefront]
    Browser -->|REST /v1, bearer token| Gateway[API Gateway]
    Gateway --> Auth[Auth service]
    Gateway --> Catalog[Catalog service]
    Gateway --> Orders[Orders service]
    Gateway --> Payments[Payments service]
    Gateway --> Inventory[Inventory service]
    Notifications[Notifications service]

    Auth --- AuthDB[(auth DB)]
    Catalog --- CatalogDB[(catalog DB)]
    Orders --- OrdersDB[(orders DB + inbox/outbox)]
    Payments --- PaymentsDB[(payments DB + outbox)]
    Inventory --- InventoryDB[(inventory DB)]
    Notifications --- NotificationsDB[(notifications DB + receipts)]

    Orders -->|ASK / HTTP| Catalog
    Orders -->|ASK / HTTP| Inventory
    Orders -->|ASK / HTTP| Payments
    Payments -->|ASK / HTTP: verify owner and amount| Orders

    Payments -->|Outbox relay| Rabbit[(RabbitMQ: shopeasy.events)]
    Orders -->|Outbox relay| Rabbit
    Rabbit -->|PaymentConfirmed, OrderShipped, OrderDelivered| Orders
    Rabbit -->|OrderPlaced, OrderPaid, shipment facts| Notifications
    Shipping[External Shipping producer] -->|OrderShipped, OrderDelivered| Rabbit
```

The six PostgreSQL databases are separate logical databases on the one local
PostgreSQL container. Each service connects only to its own database. The
arrows crossing a service boundary are HTTP requests or broker messages.

## Successful checkout sequence

```mermaid
sequenceDiagram
    actor Customer
    participant Web as Next.js
    participant Gateway
    participant Orders
    participant Catalog
    participant Inventory
    participant Payments
    participant Broker as RabbitMQ
    participant Notifications

    Customer->>Web: Add product / submit checkout
    Web->>Gateway: REST request with bearer + correlation ID
    Gateway->>Orders: Forward /v1 request
    Orders->>Catalog: ASK current product and price
    Catalog-->>Orders: Product details and price
    Orders->>Orders: Save order + OrderPlaced outbox row
    Orders->>Inventory: ASK to reserve stock
    Inventory-->>Orders: Reservation result
    Orders->>Payments: ASK for mock payment outcome
    Payments->>Orders: ASK to verify order and amount
    Orders-->>Payments: Owned order and amount
    Payments->>Payments: Save payment + PaymentConfirmed outbox row
    Payments-->>Orders: Immediate mock outcome
    Orders-->>Gateway: Checkout result (may be PENDING_PAYMENT)
    Gateway-->>Web: Response
    Payments->>Broker: Outbox relay publishes PaymentConfirmed
    Broker->>Orders: Deliver PaymentConfirmed
    Orders->>Inventory: Commit reservation (idempotent ASK)
    Orders->>Orders: Save PAID + inbox receipt + OrderPaid outbox
    Orders->>Broker: Outbox relay publishes OrderPaid
    Broker->>Notifications: Deliver OrderPaid independently
    Notifications->>Notifications: Record event receipt once
```

Orders and Notifications subscribe to event queues independently. The
Notifications service records selected event receipts; no email delivery is
implemented. If the local mock returns `FAILED`, Orders releases the stock
reservation and cancels the order; `PaymentConfirmed` is not emitted.
