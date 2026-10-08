# ShopEasy frontend

Next.js App Router storefront using TypeScript and Tailwind CSS. The browser calls
the ShopEasy API Gateway at `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000`) and never connects to a bounded-context service
directly.

## Local development

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Start the API stack from the repository root with
`docker compose up --build`. The frontend uses the real catalog, inventory,
authentication, cart, checkout, and order endpoints; an empty catalog remains
empty in the UI.

## Authentication and checkout notes

The access token is kept in `sessionStorage`, so it is removed when the browser
session ends. This browser-only bearer-token approach matches the gateway API;
the current Auth API does not provide refresh tokens, password recovery, profile
editing, or an HttpOnly-cookie session. Carts are owned by the authenticated
user. The Orders API has no active-cart discovery endpoint, so this frontend
stores the API-created cart ID in `localStorage` scoped to the user's ID.

The checkout API currently exposes only a mock payment provider. Checkout
therefore asks the user to choose a simulated success or decline and does not
collect card details. Payment confirmation reaches Orders asynchronously, so
the payment result and order tracking pages poll while the order is pending.

Run `npm run build` to build the production app. The Docker Compose frontend
publishes port 3000 and is configured to call the host gateway at port 8000.
