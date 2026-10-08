# ShopEasy storefront

The Next.js App Router application lives in `frontend/`. It is a presentation
client: catalog, inventory, cart, checkout, authentication, and order facts come
from the versioned API through the gateway. The browser never connects directly
to a service database or internal service endpoint.

## Customer pages

The storefront includes the home page, searchable and filterable catalog,
product details, cart, multi-step checkout, payment result, orders, order
tracking, sign-in, registration, and profile. Product and account data are
loaded from the APIs. Empty catalog and order responses stay empty rather than
being filled with demonstration records. If a product has no image URL, the UI
labels a neutral placeholder instead of inventing a product photo.

Orders and carts require authentication. Access tokens are kept in browser
`sessionStorage` and sent as bearer tokens to the gateway. This matches the
current token API, which does not issue refresh tokens or provide an HttpOnly
cookie session. The API-created cart ID is stored in `localStorage` under the
authenticated user's ID because the Orders API does not have an endpoint for
discovering an existing active cart. The service still checks ownership on
every cart request.

Checkout follows the backend contract: an address, then a mock payment outcome,
then an order review. It does not collect card information. The checkout
idempotency key is reused for retries in the current browser session. A
successful checkout may initially return `PENDING_PAYMENT`; the result and
tracking pages poll the order status until Orders consumes the payment event.
The API does not expose a separate intermediate `PaymentConfirmed` order
status, so the timeline shows Payment Confirmed and Paid together when the
current order state reaches `PAID` or beyond.

The cart API can increment a quantity, set an absolute quantity with one
`PUT`, or remove an item. The `PUT` keeps a quantity change in one Orders
transaction, so a timeout cannot leave a removed line waiting for a second
request to restore it.

## Run

Copy `.env.example` to `.env`, configure the backend secrets as described in
[`authentication.md`](authentication.md), then run `docker compose up --build`.
Open `http://localhost:3000`; the browser uses `http://localhost:8000` as the
single public API entry point. For local frontend development, run `npm install`
and `npm run dev` in `frontend/` while the gateway stack is running.
