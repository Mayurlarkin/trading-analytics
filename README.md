# Trading Analytics

Full-stack trade analytics: import MT5 trade history, get equity curves, drawdown and per-instrument / per-session performance stats.

> **Status: Phase 1 in progress.** Database schema, migrations and a secured trade-ingestion API are in place. The MT5 file importer, analytics and dashboard follow (see [Roadmap](#roadmap)).

<!-- Add a CI badge once the repo is on GitHub:
![CI](https://github.com/<you>/<repo>/actions/workflows/ci.yml/badge.svg) -->

## Stack

| Layer | Tech |
|---|---|
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic (migrations) |
| Database | MySQL 8.4 |
| Web | React 19, TypeScript, Vite |
| Tests | pytest, Vitest + Testing Library |
| Tooling | Ruff, oxlint, Docker Compose, GitHub Actions |

## Architecture

```
┌──────────────┐   HTTP/JSON   ┌──────────────┐   SQL    ┌──────────┐
│  React web   │ ────────────▶ │  FastAPI API │ ───────▶ │  MySQL   │
│  (Vite, TS)  │               │              │          │          │
└──────────────┘               └──────▲───────┘          └──────────┘
                                      │ POST /ingest/trades (API key)
                               ┌──────┴───────┐
                               │ MT5 EA / CLI │
                               └──────────────┘
```

## Quick start (Docker)

Requires Docker with Compose.

```bash
cp .env.example .env        # optional: defaults work for local use
docker compose up --build
```

- Web: http://localhost:8080
- API docs: http://localhost:8000/docs
- The home page shows live API and database status.

## Ingesting trades

Trades are sent to `POST /ingest/trades` by an EA or script, authenticated with a per-account API key.

**1. Create an account and key** (the key is shown once; only its hash is stored):

```bash
docker compose exec api python -m app.cli create-account \
  --email you@example.com --label "IFX Demo" --broker IFX --demo
```

**2. Send trades** (PowerShell: use `curl.exe`, since `curl` is an alias for something else):

```bash
curl.exe -X POST http://localhost:8000/ingest/trades \
  -H "X-API-Key: ta_..." -H "Content-Type: application/json" \
  -d @.github/smoke/trades.json
# {"received":1,"created":1,"updated":0,"unchanged":0}
```

Sending the same trades again returns `"unchanged":1`. You can also try it interactively at http://localhost:8000/docs (click **Authorize**).

Revoke a key with `python -m app.cli revoke-api-key <prefix>` (the first 11 characters of the key).

### Design decisions

- **Idempotent by `(account, ticket)`.** An EA can safely retry or re-send history; identical data is a no-op, changed data updates the row, new data is inserted. A concurrent duplicate insert hits the unique constraint and is retried once.
- **UTC everywhere.** Timestamps must include a timezone offset and are stored as UTC (MySQL `DATETIME` has no timezone, so a custom column type enforces the convention). Broker server time is the sender's job to convert.
- **Exact money.** `DECIMAL` columns and Python `Decimal`, never floats. Over-precise values (e.g. 3 decimals on a profit) are rejected rather than silently rounded.
- **All-or-nothing batches.** One invalid trade rejects the whole request (HTTP 422) so a bad batch can't half-apply. Max 500 trades per request.
- **API keys are hashed** (SHA-256, fine for 256-bit random keys) and individually revocable.
- **Migrations are the source of truth.** Tests build the schema with Alembic, a test fails if migrations drift from the models, and the whole suite also runs against real MySQL in CI.

## Local development

Run only the database in Docker, and the API and web app on your machine for fast reloads.

```bash
# 1. Database (exposed on localhost:3307)
docker compose up -d db

# 2. API  (Python 3.12+)
cd api
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DATABASE_URL="mysql+pymysql://trading:trading@localhost:3307/trading"
uvicorn app.main:app --reload

# 3. Web  (Node 22+), in another terminal
cd web
npm install
npm run dev                                             # http://localhost:5173
```

## Tests and checks

```bash
# API
cd api && ruff check . && ruff format --check . && pytest

# Web
cd web && npm run lint && npm test && npm run build
```

API tests run on in-memory SQLite by default, so they need no running database. To run the same suite against MySQL (as CI does), use a **separate, throwaway database**: the tests wipe and rebuild it.

```bash
docker compose up -d db
docker compose exec db mysql -uroot -proot -e "CREATE DATABASE IF NOT EXISTS trading_test"

cd api
# bash:        TEST_DATABASE_URL="mysql+pymysql://root:root@localhost:3307/trading_test" pytest -q
# PowerShell:  $env:TEST_DATABASE_URL="mysql+pymysql://root:root@localhost:3307/trading_test"; pytest -q
```

(`root:root` are the default local credentials from `docker-compose.yml`; adjust if you changed them in `.env`.)

CI also builds the full Docker Compose stack, creates an account, and sends a trade through the live API twice to prove idempotency.

## Roadmap

- [x] **Phase 0:** foundations (repo, Compose, CI, health checks)
- [x] **Phase 1a:** data model, migrations, secured idempotent ingest API, CLI
- [ ] **Phase 1b:** MT5 statement/CSV importer (needs a sample export)
- [ ] **Phase 1c:** MQL5 EA snippet that posts closed trades
- [ ] **Phase 2:** analytics engine (equity, drawdown, expectancy, breakdowns)
- [ ] **Phase 3:** API + auth
- [ ] **Phase 4:** React dashboard
- [ ] **Phase 5:** backtester *(stretch)*
- [ ] **Phase 6:** real-time updates *(stretch)*
- [ ] **Phase 7:** hardening + free-tier deploy + demo mode
- [ ] **Phase 8:** portfolio polish

## Disclaimer

For analysis and education only. Not financial advice.
