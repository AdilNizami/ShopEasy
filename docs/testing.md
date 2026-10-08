# Tests and verification

## Backend tests

Install Python 3.12, then run these commands from the repository root in
PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

Useful focused tests:

```powershell
python -m pytest tests/test_domain_rules.py -q
python -m pytest tests/test_checkout_flow.py tests/test_api_boundaries.py -q
python -m pytest tests/test_event_integration.py tests/test_outbox_pattern.py -q
python -m pytest tests/test_phase6_failure_handling.py tests/test_authentication.py -q
```

The tests use SQLite and fake HTTP/RabbitMQ adapters where practical. They
cover domain rules, request validation and ownership, event contracts and
consumers, duplicate delivery, retry/DLQ routing, Outbox behavior, auth, and
circuit breaking. Passing these tests does not by itself prove the RabbitMQ
container topology or a complete real-browser checkout; use the Compose demo
for those checks.

## Event and API contracts

The backend suite checks that event JSON Schemas are valid Draft 2020-12
schemas and compares service routes with the OpenAPI document. Run the full
suite after changing either `contracts/events/` or
`contracts/openapi/shop-easy-v1.yaml`.

## Frontend

There is currently no frontend unit-test or browser E2E script. Install
dependencies and verify a production build with:

```powershell
cd frontend
npm install
npm run build
```

The Next.js package currently has no committed lockfile, so `npm install` can
resolve newer compatible transitive versions over time. For reproducible
builds, add and review a lockfile before depending on this as a release check.

## Live-stack verification

Start the stack and work through the customer journey in
[`demo-guide.md`](demo-guide.md). To demonstrate the broker outage/Outbox
recovery scenario, stop and restart RabbitMQ using the commands in that guide.
The Python event tests simulate retry and DLQ routing; they are not a substitute
for broker-backed fault-injection tests.
