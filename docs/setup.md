# Local setup

The easiest complete demo runs all services in Docker Compose. You need Docker
Desktop (or Docker Engine) with the Compose plugin. The web app opens on
`http://localhost:3000`; its API base URL is the Gateway at
`http://localhost:8000`.

## 1. Prepare environment values

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace `AUTH_JWT_SECRET` with a random secret of at least 32
bytes. If Python is installed on the host, generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the result into `.env`. The values beginning with `local_` are demo-only
database and RabbitMQ passwords. Keep `.env` private and do not commit it.
Compose requires `AUTH_DB_USER`, `AUTH_DB_PASSWORD`, and `AUTH_JWT_SECRET` to
be set. `.env.example` provides local values for the database users/passwords
but intentionally leaves the JWT secret blank.

The main settings are grouped as follows:

| Settings | Purpose |
|---|---|
| `*_DB_USER`, `*_DB_PASSWORD` | Separate local PostgreSQL credentials for each context |
| `*_DATABASE_URL` | Connection URL for that one context's database |
| `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | Local broker access for publishers, consumers, and Gateway telemetry |
| `AUTH_JWT_SECRET`, `AUTH_ACCESS_TOKEN_TTL_SECONDS` | Token signing secret and lifetime |
| `ENGINEERING_OPERATOR_IDS` | Comma-separated Auth user IDs that should receive the operator role |
| `NEXT_PUBLIC_API_BASE_URL`, `GATEWAY_FRONTEND_ORIGINS` | Browser-to-Gateway URL and allowed local frontend origin |
| `GATEWAY_*TIMEOUT*`, `DOWNSTREAM_TIMEOUT_SECONDS` | Gateway and service HTTP timeout values |

When customizing a database password, update both the matching database user
password and that service's URL in `.env`. The local defaults are for running
the fellowship demo only, not for a deployed environment.

## 2. Start ShopEasy

```powershell
docker compose up --build
```

The first build downloads the Python and Node base images and dependencies, so
it can take a few minutes. Open `http://localhost:3000`. The API liveness check
is `http://localhost:8000/health/live`. The product catalog starts empty; use
the [demo guide](demo-guide.md) to create a demonstration product and set its
stock through the owning services' APIs.

Stop the stack with `Ctrl+C`. To stop detached containers, run
`docker compose down`. This keeps the named PostgreSQL volume. **Do not run
`docker compose down -v` unless you intend to permanently remove local ShopEasy
database data.**

For older local PostgreSQL volumes that were created before the Auth database
was added, use the safe setup in [authentication docs](authentication.md#database-setup-and-existing-local-volumes).

## 3. Optional local development

The frontend can run outside Docker while backend services run in Compose:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Its `NEXT_PUBLIC_API_BASE_URL` defaults to the
host Gateway at port 8000. The frontend has no test script; see
[`testing.md`](testing.md) for the available verification commands.

For a backend-only local environment, install Python 3.12 and the development
requirements, then follow the test setup in [`testing.md`](testing.md). The
normal integrated run is Compose, which starts six FastAPI services plus
PostgreSQL, RabbitMQ, and the Next.js app.
