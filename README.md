# Trading Analytics

Full-stack trade analytics: import MT5 trade history, get equity curves, drawdown and per-instrument / per-session performance stats.

> **Status: dashboard started.** Trades arrive from an MT5 report or a live EA through a secured, idempotent API; the analytics engine turns them into equity, drawdown and breakdown statistics; and a React dashboard (login, accounts, overview with balance and drawdown charts) shows them. Trades table, breakdowns, import and key management pages come next (see [Roadmap](#roadmap)).

<!-- Add a CI badge once the repo is on GitHub:
![CI](https://github.com/<you>/<repo>/actions/workflows/ci.yml/badge.svg) -->

## Stack

| Layer | Tech |
|---|---|
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic (migrations) |
| Database | MySQL 8.4 |
| Web | React 19, TypeScript, Vite, React Router, TanStack Query, hand-built SVG charts |
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

- Web: http://localhost:8080 (log in with the user you create below)
- API docs: http://localhost:8000/docs
- The login page and the footer show live API and database status.

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
   Logged in instead of holding an API key? Use **POST /accounts/{id}/import/mt5-report** the same way.
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

## Analytics

`api/app/analytics` is a set of pure functions: closed trades in, plain numbers out, with no database or web code, so every metric is tested against figures worked out by hand. See your own numbers now:

```
docker compose exec api python -m app.cli stats --account-id 1
```

It prints the summary (win rate, profit factor, expectancy, streaks, drawdown, recovery factor) and tables by instrument, session and weekday.

**Definitions** (so the numbers can be audited)
- A trade's result is its **net**: profit + commission + swap. A *win* is net above zero, a *loss* below zero, and exactly zero is *break-even*, counted separately. (MT5's own report counts break-even trades as profit trades, so its win rate can differ slightly.)
- The **equity curve** is a closed-trade balance: starting balance plus each position's net result, in order of closing. Floating profit on open positions is not included.
- **Drawdown** is the fall from the highest balance reached so far, with the starting balance as the first peak. The deepest drawdown is reported by amount and by percentage (often the same dip), with the peak and low dates and whether the balance got back to the peak. *Absolute drawdown* is the starting balance minus the lowest balance. *Recovery factor* is net profit divided by the deepest drawdown.
- **Profit factor** is gross profit divided by gross loss; it is left empty (not infinite) when nothing was lost.
- **Weekday, hour and session** use the time the trade was *opened*, on a chosen clock (New York by default). Sessions are half-open hour ranges on that clock (defaults: Asia 19-02, London 02-07, New York AM 07-12, New York PM 12-17, After hours 17-19) and can be replaced.
- **Symbols** are grouped by a common name: the broker suffix is dropped and a small alias table maps known broker names (for example `T100.IFX_M` to `NAS100`). The database keeps the symbol exactly as sent.

**Validation.** The formulas were also checked against the broker's own *Results* block of a real report, using its closing deals: net, gross profit and loss, profit factor, expected payoff, recovery factor, all three drawdown figures, trade count, largest and average loss, and both streaks matched exactly. The only differences were the break-even convention above. The real report is not in this repository.

**Not yet:** a Sharpe-style ratio (MT5's own formula was not reproducible, so it will be added with an explicit definition), and deposits/withdrawals in the equity curve (the starting balance is used instead).

## API and login

Two kinds of caller, two kinds of credential:

| Who | Credential | Can do |
|---|---|---|
| A person (dashboard, `/docs`) | email + password, giving a login token | read their own accounts' analytics |
| A machine (EA, script) | per-account API key | send trades and import reports |

A login token cannot send trades and an API key cannot read analytics, so a leaked EA key cannot be used to browse anything. (People can also *manage* accounts, keys and imports with their login, see below.)

**Log in once** (there is no public sign-up yet; users are created from the command line):

```
docker compose exec api python -m app.cli set-password --email you@example.com
```

It asks for the password twice and needs 10 to 128 characters. Then open http://localhost:8000/docs, click **Authorize**, and enter your email as the *username* with that password. Every request after that uses your token.

| Endpoint | Returns |
|---|---|
| `POST /auth/login` | a login token (valid 8 hours; set `JWT_EXPIRE_MINUTES` to change) |
| `GET /auth/me` | who you are |
| `GET /accounts` | your accounts, with trade count and last close |
| `GET /accounts/{id}/summary` | win rate, profit factor, expectancy, streaks, drawdown, recovery factor |
| `GET /accounts/{id}/equity-curve` | balance after every trade, with running peak and drawdown |
| `GET /accounts/{id}/breakdown?by=instrument\|session\|weekday\|hour&tz=...` | the same statistics per group |
| `GET /accounts/{id}/trades` | paged list; filter by `symbol`, `direction`, `result`, dates; sort by `close_time`, `open_time`, `profit`, `net` |

### Managing accounts and keys (login)

Everything the command line does for accounts is also available with a login, which is what the dashboard uses. Only the first user and account need the command line.

| Endpoint | Does |
|---|---|
| `POST /accounts` | create an account (label, broker, currency, starting balance, demo flag, broker server time); labels are unique per person, ignoring capitals |
| `PATCH /accounts/{id}` | change some settings; only the fields you send change, unknown fields are refused |
| `GET /accounts/{id}/api-keys` | list keys (label, prefix, created, revoked); the secret is never shown again |
| `POST /accounts/{id}/api-keys` | issue a key for an EA or script; **the secret is in this response only** (at most 10 active keys per account) |
| `DELETE /accounts/{id}/api-keys/{key_id}` | revoke a key; it stops working immediately |
| `POST /accounts/{id}/import/mt5-report` | import an MT5 report with a login; same rules as `/import/mt5-report` (`dry_run`, `server_time`) |

Other people's accounts and keys answer `404`, the same as ones that do not exist. To change the email you log in with: `python -m app.cli update-user --email old@example.com --new-email new@example.com`.

The analytics endpoints accept `closed_from` (inclusive) and `closed_until` (exclusive), written with a timezone such as `2026-03-01T00:00:00Z`. For a period, the starting balance is the balance at that moment, so drawdown and return are right for that window. Money is returned as strings with 2 decimals (`"-1234.50"`) and ratios as fractions with 4 (`"0.2500"` is 25%), so nothing is lost to floating point.

**Security decisions**
- Passwords are hashed with scrypt (standard library, cost stored in each hash so it can be raised later) and are never logged or echoed.
- A wrong password and an unknown email give the same answer and take the same time, so emails cannot be discovered.
- Tokens are signed (HS256) and must carry an expiry; unsigned, tampered, expired and wrong-key tokens are rejected (all tested).
- Another user's account answers `404`, exactly like one that does not exist.
- The signing secret has a development default, but the app **refuses to start** with `ENVIRONMENT` set to anything other than `development` unless `JWT_SECRET` is a random value of 32+ characters (see `.env.example`).
- Not done yet, planned for the hardening phase: login rate limiting and lockout, refresh tokens, and password reset.

## The dashboard

Open http://localhost:8080 and log in with the email and password you set (see [API and login](#api-and-login)).

- **Accounts:** your accounts with trade count, starting balance and last close; create a new one (name, currency, starting balance, demo flag, broker server time).
- **Overview:** net profit, return, win rate, profit factor, expectancy, average win and loss, max drawdown and average holding time, plus a balance chart and a drawdown chart. A period filter (all time, 12 months, 90 days, 30 days) scopes everything on the page; while a new period loads, the previous figures stay on screen, dimmed.
- **Charts** are drawn by hand in SVG (no chart library): a 2px line with a faint wash, hairline grid, an end label, a crosshair tooltip that follows the mouse or touch, and arrow-key reading for keyboard users. Each chart has a **Show table** view of the same numbers. Colors come from one colour-blind-checked palette with a dark theme that follows your system setting.

How it talks to the API: `src/api/http.ts` is one small request function (token in, `ApiError` out); `src/auth` holds the login token (in `sessionStorage`, so it ends with the tab) and logs out when the API says the token is no longer valid; `src/api/queries.ts` wraps each endpoint in a TanStack Query hook. Money stays a string until the moment it is drawn or formatted. The API must list the web address in `CORS_ORIGINS` (Compose already does for `http://localhost:8080`; use `localhost`, not `127.0.0.1`).

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
# (the API's CORS_ORIGINS defaults to this address; VITE_API_URL points the web app at the API)
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
- [x] **Phase 1c:** MQL5 reporter EA that posts closed trades
- [x] **Phase 2:** analytics engine (equity, drawdown, expectancy, breakdowns) and a `stats` CLI command
- [x] **Phase 3a:** login + read endpoints over the analytics
- [x] **Phase 3b:** manage accounts and API keys, and import reports, with a login
- [x] **Phase 4a:** React dashboard: login, accounts, overview with balance and drawdown charts
- [ ] **Phase 4b:** trades table, breakdown charts, import page, account settings and API key management
- [ ] **Phase 5:** backtester *(stretch)*
- [ ] **Phase 6:** real-time updates *(stretch)*
- [ ] **Phase 7:** hardening + free-tier deploy + demo mode
- [ ] **Phase 8:** portfolio polish

## Disclaimer

For analysis and education only. Not financial advice.
