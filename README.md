# Trading Analytics

Full-stack trade analytics: import MT5 trade history, get equity curves, drawdown and per-instrument / per-session performance stats.

> **Status: Phase 1 (data in) nearly done.** Trades can be imported from an MT5 report or posted by an EA through a secured, idempotent API. Analytics and the dashboard come next (see [Roadmap](#roadmap)).

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
                       POST /import/mt5-report │ POST /ingest/trades
                              (API key, both)  │
                               ┌──────┴───────┐
                               │ MT5 report / │
                               │ MQL5 EA /    │
                               │ scripts      │
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

## Getting trades in

There are two ways in. Both use a per-account API key and both are safe to repeat.

| | Use it to | Endpoint |
|---|---|---|
| MT5 report upload | back-fill history from an Excel export | `POST /import/mt5-report` |
| JSON ingest | send trades live from an EA or script | `POST /ingest/trades` |

The easiest way to try either is the interactive docs at http://localhost:8000/docs: click **Authorize**, paste your key, then **Try it out** on any endpoint.

### 1. Create an account (once)

The key is shown once; only its hash is stored. Type it as one line:

```
docker compose exec api python -m app.cli create-account --email you@example.com --label "IFX Demo" --broker IFX --currency ZAR --server-time ny_close --demo
```

Already have an account? Set its currency and broker clock with
`docker compose exec api python -m app.cli update-account --account-id 1 --currency ZAR --server-time ny_close`.
Revoke a key with `python -m app.cli revoke-api-key <prefix>` (the first 11 characters of the key).

### 2. Import an MT5 report

1. In MT5, open the **History** tab, choose the date range, right-click, **Report**, **Open XML (MS Excel)**. The report must be in English.
2. In the docs page, open **POST /import/mt5-report**, **Try it out**, choose the file and **Execute**. Set `dry_run` to `true` first to preview the counts without saving anything.
3. Or from a terminal (PowerShell: use `curl.exe`; `curl` is an alias for something else):

```
curl.exe -X POST "http://localhost:8000/import/mt5-report?dry_run=true" -H "X-API-Key: ta_..." -F "file=@C:\path\to\ReportHistory.xlsx"
```

The response says how many positions were created, updated or unchanged, plus any warnings:

```json
{"positions_in_report": 628, "created": 628, "updated": 0, "unchanged": 0, "dry_run": false,
 "server_time": "ny_close", "report": {"currency": "ZAR", "account_kind": "demo", "margin_mode": "hedge", ...},
 "warnings": []}
```

- Only the **Positions** section (closed positions) is imported. The Orders and Deals sections and the summary are ignored, apart from the report's own *Total Net Profit*, which is used as a cross-check (a mismatch produces a warning).
- Import the same file again, or a newer export that includes older trades, and only new or changed positions are touched.
- Any invalid row rejects the whole file with a list of the offending rows (by spreadsheet row number), so nothing is half-imported.

**Broker server time.** MT5 reports carry no timezone. Times are the broker server's clock, so the importer needs to know how to read it: `ny_close` (New York time + 7 hours, i.e. UTC+2 in winter and UTC+3 in summer, switching on the *US* daylight-saving dates; typical for IFX) or any IANA zone such as `Europe/Athens` or `UTC`. It is stored on the account, or passed per upload as `server_time`. If neither is set the import is refused rather than guessing.

### 3. Send trades live from MT5

`mql5/TradeReporterEA.mq5` is a small Expert Advisor that reports every closed position of the account. It never places or changes orders, so run it on its own chart next to your trading EA; your EA does not need to change. Developers who prefer to embed it can `#include "TradeReporter.mqh"` and call `Init`, `Sync` (from `OnTimer` and on `TRADE_TRANSACTION_DEAL_ADD`) as the example does.

**Set up**
1. Copy the `mql5` folder into MT5 (**File, Open Data Folder**, then `MQL5\Experts\TradingAnalytics\`). Open `TradeReporterEA.mq5` in MetaEditor and press **F7** to compile; it should say 0 errors.
2. In MT5 open **Tools, Options, Expert Advisors**, tick **Allow WebRequest for listed URL** and add `http://127.0.0.1:8000`. MT5 blocks every web call until the address is listed.
3. Make sure **Algo Trading** is switched on in the toolbar, then drag **TradeReporterEA** onto any chart and fill in the inputs: `InpApiKey` (your `ta_...` key) and, if you like, `InpStrategyTag`. Leave `InpTimeMode` on NY-close for IFX.
4. **Try it safely first:** set `InpPreviewOnly` to true. The Experts tab prints the JSON for your newest closed trades and sends nothing, so you can compare it with the MT5 report. Then set it back to false.

**Behaviour**
- Checks every 15 seconds and whenever a deal is added; one record per *fully closed* position (partial closes are reported once the position is finished).
- If the API is down or the key is wrong nothing is lost: it remembers the last position it delivered (terminal global variable `TA_LAST_CLOSE_<login>`) and resumes from there, even after an MT5 restart. Re-sending is harmless because the API ignores duplicates.
- On the very first run it sends the last `InpBackfillDays` (default 7) days. For older history use the report import above.
- A trade the API rejects is logged and skipped so it cannot block the ones after it.
- It does nothing in the Strategy Tester, so backtests never reach your real data.
- Positions are matched with the report importer on the position ticket, so a trade sent by the EA and later found in a report is recognised as the same one. A tag set by the EA is kept when a report without tags is imported.
- Assumptions to know about: hedging accounts only (it warns on netting); exchange fees, if your broker charges any, are added into the commission figure; times are converted with the same NY-close rule as the importer (a test checks the algorithm against the API for four years of daylight-saving changes).
- Treat the key like a password: do not share screenshots of the inputs, and keep saved presets (`*.set`) out of git (they are git-ignored here).

**Or post JSON yourself** (any language or script):

```
curl.exe -X POST http://localhost:8000/ingest/trades -H "X-API-Key: ta_..." -H "Content-Type: application/json" -d "@.github/smoke/trades.json"
# {"received":1,"created":1,"updated":0,"unchanged":0}
```

Timestamps here must already carry a timezone offset (they are stored as UTC), so the sender converts. Sending the same trades again returns `"unchanged":1`.

### Design decisions

- **Idempotent by `(account, ticket)`.** An EA or importer can safely retry or re-send history; identical data is a no-op, changed data updates the row, new data is inserted. A concurrent duplicate insert hits the unique constraint and is retried once.
- **One validation path.** The report importer builds the same models the JSON endpoint validates, so both accept and reject exactly the same data.
- **UTC everywhere.** Timestamps are stored as UTC (MySQL `DATETIME` has no timezone, so a custom column type enforces the convention). Broker clocks are converted explicitly, using a rule that follows US daylight saving, because a fixed European zone is an hour out for a few weeks each spring and autumn (this is covered by tests).
- **Exact money.** `DECIMAL` columns and Python `Decimal`, never floats. Over-precise values (e.g. 3 decimals on a profit) are rejected rather than silently rounded.
- **All-or-nothing.** One invalid trade (or report row) rejects the whole request, so a bad batch can't half-apply. The JSON endpoint takes at most 500 trades per request; file imports are not limited by that.
- **Reconciliation.** Imported profit + commission + swap is compared with the report's own total, so missing or misread rows are caught.
- **Untrusted uploads.** 10 MB upload limit, the workbook is checked for abnormal expansion (zip bombs) and opened in read-only mode.
- **API keys are hashed** (SHA-256, fine for 256-bit random keys) and individually revocable.
- **Migrations are the source of truth.** Tests build the schema with Alembic, a test fails if migrations drift from the models, and the whole suite also runs against real MySQL in CI.

### Known limitations

- Broker symbols are stored as exported (e.g. `T100.IFX_M`, `WS30.IFX_M`); mapping them to common names such as NAS100 and US30 is planned.
- Deposits, withdrawals and the starting balance (the report's Deals section) are not imported yet; the equity curve work will need them.
- Only English-language `.xlsx` reports are supported; HTML reports are not.
- The upload limit is enforced by the app; a request-size limit at the web server comes with the deployment hardening phase.

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

CI also builds the full Docker Compose stack against a fresh MySQL, then through the live API: creates an account, sends a trade twice, and imports a sample MT5 report twice to prove idempotency. The sample report (`api/tests/fixtures/mt5_sample_report.xlsx`) is synthetic; regenerate it with `python -m tests.mt5_builder`.

> **Never commit real trading history.** `.gitignore` excludes `*.xlsx` outside the test fixtures. Keep your own exports outside the repo.

## Roadmap

- [x] **Phase 0:** foundations (repo, Compose, CI, health checks)
- [x] **Phase 1a:** data model, migrations, secured idempotent ingest API, CLI
- [x] **Phase 1b:** MT5 Excel report importer
- [ ] **Phase 1c:** MQL5 reporter EA that posts closed trades *(written and its algorithm tested; waiting for the first compile and run in MT5)*
- [ ] **Phase 2:** analytics engine (equity, drawdown, expectancy, breakdowns)
- [ ] **Phase 3:** API + auth
- [ ] **Phase 4:** React dashboard
- [ ] **Phase 5:** backtester *(stretch)*
- [ ] **Phase 6:** real-time updates *(stretch)*
- [ ] **Phase 7:** hardening + free-tier deploy + demo mode
- [ ] **Phase 8:** portfolio polish

## Disclaimer

For analysis and education only. Not financial advice.
