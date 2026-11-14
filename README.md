# Trading Analytics

Full-stack trade analytics: import MT5 trade history, get equity curves, drawdown and per-instrument / per-session performance stats.

> **Status: Phase 0 (foundations).** The skeleton runs end to end: API, database, web app, tests, CI. Features land phase by phase (see [Roadmap](#roadmap)).

<!-- Add a CI badge once the repo is on GitHub:
![CI](https://github.com/<you>/<repo>/actions/workflows/ci.yml/badge.svg) -->

## Stack

| Layer | Tech |
|---|---|
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Database | MySQL 8.4 |
| Web | React 19, TypeScript, Vite |
| Tests | pytest, Vitest + Testing Library |
| Tooling | Ruff, oxlint, Docker Compose, GitHub Actions |

## Architecture

```
┌──────────────┐   HTTP/JSON   ┌──────────────┐   SQL    ┌──────────┐
│  React web   │ ────────────▶ │  FastAPI API │ ───────▶ │  MySQL   │
│  (Vite, TS)  │               │  /health ... │          │          │
└──────────────┘               └──────────────┘          └──────────┘
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

API unit tests use in-memory SQLite, so they need no running database. CI also builds the full Docker Compose stack and checks that the API can reach MySQL.

## Roadmap

- [x] **Phase 0:** foundations (repo, Compose, CI, health checks)
- [ ] **Phase 1:** data model + trade ingestion (MT5 import, EA webhook)
- [ ] **Phase 2:** analytics engine (equity, drawdown, expectancy, breakdowns)
- [ ] **Phase 3:** API + auth
- [ ] **Phase 4:** React dashboard
- [ ] **Phase 5:** backtester *(stretch)*
- [ ] **Phase 6:** real-time updates *(stretch)*
- [ ] **Phase 7:** hardening + free-tier deploy + demo mode
- [ ] **Phase 8:** portfolio polish

## Disclaimer

For analysis and education only. Not financial advice.
