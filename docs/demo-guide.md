# Fellowship demonstration guide

This guide follows the implemented flow and uses the local mock payment
provider. It does not create sample products automatically: Catalog and
Inventory start empty. Create one product and its stock before the live
checkout.

## Prepare one operator/shopper account

Start the stack using [local setup](setup.md). In a new PowerShell window at
the repository root, register a demo account. Pick a unique username and a
password with at least 12 characters:

```powershell
$credentials = @{ username = "demo_architect"; password = "Replace-With-A-Long-Local-Password" } | ConvertTo-Json
$account = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/v1/auth/register" -ContentType "application/json" -Body $credentials
$account.userId
```

Add the printed UUID to `.env` as `ENGINEERING_OPERATOR_IDS=<uuid>`. For
example, if the response contains `11111111-2222-4333-8444-555555555555`, set:

```dotenv
ENGINEERING_OPERATOR_IDS=11111111-2222-4333-8444-555555555555
```

Recreate Auth so it reads the allowlist, then log in again in the browser. The
first access token was issued before allowlisting and still has the customer
role.

```powershell
docker compose up -d --force-recreate auth
```

The account remains a normal shopper for its own cart and orders, and gains
operator-only product setup and engineering dashboard access. For a
customer-vs-operator authorization demo, use a second account that is not in
the allowlist.

## Add one product and stock

Get a fresh operator token from Auth and create a product through the public
Gateway. Replace the password with the same local account password:

```powershell
$credentials = @{ username = "demo_architect"; password = "Replace-With-A-Long-Local-Password" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/v1/auth/login" -ContentType "application/json" -Body $credentials
$headers = @{ Authorization = "Bearer $($login.accessToken)" }
$productBody = @{
  name = "Demo Coffee"
  description = "A product created through the Catalog API for the checkout demonstration."
  price = @{ amount = "12.50"; currency = "USD" }
  sellable = $true
} | ConvertTo-Json -Depth 5
$product = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/v1/products" -Headers $headers -ContentType "application/json" -Body $productBody
$product | Select-Object id, name, price
```

Inventory stock administration is intentionally marked internal and is not
routed through the public Gateway. Initialize it by calling the Inventory
service's own HTTP API **from inside its own container** (this never accesses
the database directly):

```powershell
$stockScript = "import json, urllib.request; url = 'http://localhost:8000/v1/inventory/stock/$($product.id)'; request = urllib.request.Request(url, data=json.dumps({'quantityOnHand': 5}).encode(), headers={'Content-Type': 'application/json'}, method='PUT'); print(urllib.request.urlopen(request).read().decode())"
docker compose exec -T inventory python -c $stockScript
```

Open `http://localhost:3000`, sign in with the demo account, and confirm
`Demo Coffee` appears in Products. Its displayed stock comes from Inventory's
availability API; the product data itself comes from Catalog.

## Customer journey: successful checkout

1. Open the product detail page and add one item to the cart. Orders creates
   and owns the cart; the browser keeps only the cart ID for that user.
2. Open the cart and continue to Checkout. Enter a sample delivery address.
3. Select **Simulate successful payment**. This is a mock provider choice, not
   a card payment.
4. Place the order. Orders rechecks current Catalog price, reserves stock via
   Inventory, and asks Payments to run the mock outcome. The immediate response
   may be `PENDING_PAYMENT` because paid status waits for event processing.
5. Follow the payment result/tracking page. Orders consumes `PaymentConfirmed`,
   commits the reservation, changes the order to `PAID`, then emits `OrderPaid`.
6. Sign in to the engineering dashboard at `/engineering`. It is read-only and
   operator-only. Inspect event IDs/types/producers, service health, Orders and
   Payments Outbox rows, and Notifications' processed receipts.

The local mock supports `mock-success` and `mock-failure`. There are no card
details, external payment provider, email messages, or in-repository Shipping
service.

## Failure demonstration: broker outage and Outbox recovery

Use the operator account and keep the engineering dashboard open:

```powershell
docker compose stop rabbitmq
```

Place an order with the successful mock payment while RabbitMQ is stopped.
Payments commits the confirmed payment and `PaymentConfirmed` Outbox row
together. Orders commits its own state and `OrderPlaced` Outbox row together.
The background relay cannot confirm broker publication, so the corresponding
rows stay pending and the order can remain `PENDING_PAYMENT`.

Look at the engineering dashboard for pending Outbox records (and RabbitMQ
health showing unavailable). Restore the broker:

```powershell
docker compose start rabbitmq
```

The relay reconnects, publishes the pending events, and marks them published
only after broker confirmation. Orders then consumes `PaymentConfirmed` and
the status should advance to `PAID`. Allow a few seconds for the relay and
consumer. The Outbox reduces event-loss risk; the message may still be
delivered twice if the process crashes after broker acceptance but before the
published marker commits. Consumers use the stable event ID to avoid repeating
the business action.

## Failure demonstration: declined mock payment

Repeat checkout but choose **Simulate declined payment**. Payments records a
failed mock attempt and does not publish `PaymentConfirmed`. Orders releases
the reservation, cancels the order, and reopens the cart. This demonstrates a
business failure, not RabbitMQ retry behavior.

## Duplicate, retry, and DLQ demonstration

The automated tests make these scenarios repeatable without risking the live
demo data. In a Python 3.12 environment, run:

```powershell
python -m pytest tests/test_outbox_pattern.py -q
python -m pytest tests/test_event_integration.py -q
python -m pytest tests/test_phase6_failure_handling.py -q
```

These tests verify duplicate event IDs, the Outbox duplicate-publication
window, transient retry scheduling, permanent validation failures, exhausted
retry DLQ routing, and malformed retry metadata. The test exchange is a fake;
these results demonstrate handler behavior and do not claim that a live
RabbitMQ poison-message injection was performed.

For more detail about routing, delay intervals, retry policy, and operational
limits, see [Phase 6 failure handling](phase6-failure-handling.md) and
[Phase 5 Outbox](phase5-outbox.md).
