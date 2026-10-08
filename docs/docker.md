# Docker Compose guide

ShopEasy's local stack is defined in [`compose.yaml`](../compose.yaml). It
contains the Next.js frontend, API Gateway, Auth, Catalog, Orders, Payments,
Inventory, Notifications, PostgreSQL, and RabbitMQ.

```powershell
# Build and start all containers in the foreground
docker compose up --build

# Or run in the background
docker compose up --build -d

# Check service/container state
docker compose ps

# Follow all logs, or one service
docker compose logs -f
docker compose logs -f orders

# Stop containers but keep local database data
docker compose down
```

Useful local addresses:

| Address | Purpose |
|---|---|
| `http://localhost:3000` | Next.js storefront |
| `http://localhost:8000` | Public API Gateway |
| `http://localhost:8000/health/live` | Gateway liveness |
| `http://localhost:15672` | RabbitMQ management console (local operations only) |

RabbitMQ management credentials come from `RABBITMQ_USER` and
`RABBITMQ_PASSWORD` in `.env`. The broker management port is bound to local
loopback. PostgreSQL and the internal service ports are not published to the
host. The browser can only call the Gateway; service-to-service HTTP and
RabbitMQ traffic use the Compose network.

To restart one service after changing its environment, recreate that service:

```powershell
docker compose up -d --force-recreate auth
```

This is useful after changing `ENGINEERING_OPERATOR_IDS`; log out and back in
afterward so Auth issues a new token with the current role. `docker compose
down` leaves the named Postgres volume intact. Removing it with `docker compose
down -v` permanently deletes local accounts, products, orders, and stock.

The Postgres init scripts run automatically only when the data volume is first
created. For an existing volume that predates Auth, see the migration steps in
[`authentication.md`](authentication.md#database-setup-and-existing-local-volumes).
