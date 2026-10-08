# Phase 10: Engineering and observability dashboard

The internal dashboard lives at `/engineering` in the Next.js frontend. It is a
read-only presentation of live service health, produced events, processed-event
receipts, outbox status, and RabbitMQ dead-letter queues. It does not expose
retry, replay, purge, payment, inventory, or order controls.

## Operator access

Normal registrations receive the `customer` role. To grant the engineering
view, add the existing Auth `userId` to the comma-separated
`ENGINEERING_OPERATOR_IDS` environment variable. Obtain that ID from the
registration/login response or `GET /v1/auth/me`. Auth includes the resulting
role in its signed access token and `/v1/auth/me` response. Restart Auth, then
sign out and sign back in to receive a token with the new role. Remove the ID
and reissue the token to revoke access. The default allowlist is empty.

The gateway checks the operator claim for every `/v1/internal/observability/*`
route. Orders, Payments, and Notifications independently check the same claim
on their internal telemetry endpoints. The dashboard also hides its navigation
link from customer accounts. A customer who types the route directly sees an
access-denied message, and their API call receives 403. Service ports are not
published to the host. RabbitMQ management is bound to host loopback for local
development; the dashboard reaches it over the private Compose network.

Gateway uses its private Compose network to probe each service readiness route
and RabbitMQ management. Service telemetry is read from the service that owns
those records: Orders and Payments return their own outbox rows, Orders returns
its inbox receipts, and Notifications returns its own processed-event records.
No service reads another context's database. Event payloads and personal data
are omitted from the dashboard.

## What the fields mean

- **Events processed** counts durable consumer receipts in Orders plus
  Notifications. One event consumed by two services contributes two
  processing actions.
- **Recent events** combines producer outbox records with consumer receipts by
  `eventId`. The event timestamp is the producer `occurredAt` when available;
  for a consumer-only external shipment fact, it is the recorded processing
  time. Retry counts are shown where they are persisted (outbox attempts or DLQ
  headers); the current inbox schema does not persist successful delivery retry
  history and displays that field as unavailable.
- **Outbox pending** counts only rows whose service-local status is `PENDING`.
  Published rows can be delivered more than once; consumers are idempotent.
- **Failed events / DLQ** are messages currently waiting in the Orders and
  Notifications dead-letter queues. The dashboard reads a small message sample
  using RabbitMQ's `ack_requeue_true` inspection mode, so messages are placed
  back on their queue and are not acknowledged or removed. If RabbitMQ's
  management API is unavailable, the dashboard shows unavailable rather than a
  false zero.
- **Service health** reports readiness checks. Database-backed services test
  their own database; RabbitMQ is probed through its management API.

The dashboard refreshes every ten seconds and supports manual refresh. It uses
the same public gateway origin as the storefront; the gateway performs the
operator check and makes private network requests with configured timeouts.
