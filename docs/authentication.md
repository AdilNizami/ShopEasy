# Phase 8: Authentication and authorization

## Registration and login

The Auth service owns user accounts in a separate `auth` database. Register at
`POST /v1/auth/register` or log in at `POST /v1/auth/login` with a username and
password. Usernames are normalized to lowercase. Passwords must be 12–128
characters and are stored only as Argon2 hashes. Login returns a short-lived
signed JWT access token; use it as `Authorization: Bearer <accessToken>`.
`GET /v1/auth/me` returns the user identity in that token. There is no refresh
token or password recovery feature in this phase.

The signing key is `AUTH_JWT_SECRET`, supplied only through the environment and
required by Compose. Generate a different random value for each environment
(for example with Python's `secrets.token_urlsafe(48)`). It must be at least 32
bytes. Auth issues tokens with issuer and audience claims, and the gateway and
Orders validate the signature, issuer, audience, and expiry. Never commit the
real key or log passwords, hashes, or tokens. `.env.example` contains only a
replacement placeholder.

## Protected routes and ownership

Product/category browsing and inventory availability are public read routes.
Registration and login are public. Product and category writes require an
allowlisted operator token; payment routes, carts, checkout, orders, and
`/v1/auth/me` require a valid bearer token. The gateway validates protected
requests before routing them. Orders validates the bearer token again inside
its own service, so it does not trust a caller-provided user ID.

Orders stores the token subject as `user_id` on each new cart and order. Every
cart read/write and checkout lookup filters by both resource ID and owner ID;
order listing, detail, and status queries do the same. A resource owned by
another user returns 404, avoiding a resource-existence oracle. Other bounded
contexts continue to own their own data; the Auth database is not queried by
Orders. Orders uses the verified token subject as its external identity.

Older local carts and orders created before authentication have a null owner.
They are intentionally not visible to registered users. Decide an explicit
operator transfer/retention policy before making existing production records
mandatory-owned; do not guess an owner during migration.

## Database setup and existing local volumes

Fresh Postgres volumes create the Auth role/database from the normal init
script. For a Postgres volume initialized before Phase 8, recreate no volumes.
Copy `.env.example`, generate the JWT secret, and start only Postgres first so
the new `AUTH_DB_USER` and `AUTH_DB_PASSWORD` values are available:

```powershell
docker compose up -d postgres
docker compose exec -T postgres psql -U shop_easy_admin -d postgres -f /tmp/phase8-auth.sql
docker compose up --build
```

The script is mounted at `/tmp/phase8-auth.sql` and is safe to run again. If
`POSTGRES_ADMIN_USER` was customized, use that configured administrator.
Orders adds nullable owner columns with an idempotent startup migration; old
rows remain inaccessible until an approved ownership policy is applied. The
Orders startup migration also adds the optional correlation ID to existing
inbox receipts so the engineering view can retain event trace context.

## Error responses

Missing, expired, malformed, or incorrectly signed tokens return a structured
401 response with `WWW-Authenticate: Bearer`. Registration validation errors
return 422; an existing username returns 409. Login uses the same generic 401
message for an unknown username and a wrong password. Authentication errors
include correlation IDs, but never credentials or token contents.

## Engineering operator role

By default every account has the `customer` role. The internal architecture
dashboard can be granted to existing accounts by listing their UUIDs in the
`ENGINEERING_OPERATOR_IDS` deployment environment variable. Auth puts the
allowlisted role in the signed access token and `/v1/auth/me`; the gateway and
telemetry-owning services require that role independently. The default is an
empty list. See [the observability dashboard guide](observability-dashboard.md)
for setup and the read-only dashboard scope.
