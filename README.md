# Mini Compute Console

[![CI](https://github.com/eliyas-05/mini-compute-console/actions/workflows/ci.yml/badge.svg)](https://github.com/eliyas-05/mini-compute-console/actions/workflows/ci.yml)

A scaled-down GPU compute marketplace with real-time job streaming, multi-tenant API design, and production-aware backend patterns — built as a portfolio project for a software engineering internship application.

---

> **See it in action:** follow [DEMO.md](DEMO.md) for a 3-minute walkthrough of every feature — live WebSocket streaming, cost forecasting, efficiency report, and multi-tenant isolation.

## What it does

VoltGrid lets you pick a GPU provider, launch a training job, and watch costs tick up and logs stream in real time — the same core loop as RunPod or Vast.ai, compressed into a clean, self-contained demo.

**Backend:** FastAPI · SQLite (raw SQL) · WebSocket pub-sub · Prometheus metrics  
**Frontend:** Vanilla JS · CSS custom properties · No build step · No framework

---

## Quick Start

**1. Start the backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Interactive docs: http://localhost:8000/docs

**2. Open the frontend**
```bash
cd frontend
python3 -m http.server 3000
# open http://localhost:3000
```

The UI ships with `demo-key-123` pre-filled — open it and click **⚡ Auto Pick & Launch**.

**Or with Docker:**
```bash
docker-compose up
# backend on :8000, frontend on :3000
```

---

## Features

### Core marketplace loop
- **8 GPU providers** (RunPod A100/H100, Vast.ai, Colo) with live spot prices
- **Jobs move through `queued → running → complete`** over ~90 seconds with simulated training logs and GPU utilisation telemetry
- **Smart priority routing** — `high` picks max-uptime, `normal` picks cheapest spot, `low` picks cheapest base
- **Auto-reroute on busy** — if a provider goes busy mid-queue, the engine retries up to 3 times and appends a log line

### Real-time streaming (two WebSocket channels)
| Channel | Path | What it does |
|---------|------|-------------|
| Per-job | `WS /ws/jobs/{id}/logs` | Log lines + GPU util for the active job |
| Global pub-sub | `WS /ws/events` | All job state changes broadcast to every connected tab |

The global channel uses a fan-out hub (`pubsub.py`). Job engine fires `broadcast_sync()` on every transition — no polling anywhere.

### Spot price simulation
Prices follow an **Ornstein-Uhlenbeck mean-reverting random walk** (θ=0.15, σ=0.04·base), the same process used in real spot market models. The UI shows `▲`/`▼`/`—` trend signals per provider.

### Multi-tenant namespacing
Every job is stamped with an `owner` derived from the API key. All read operations filter by owner — cross-tenant access returns 404 (not 403) to avoid leaking job existence.

### Budget guardrails
Pass `budget_limit` on launch. `check_budget()` is called on every poll — no background thread. When `cost_so_far >= budget_limit`, the job auto-cancels, logs the reason, and broadcasts a pub-sub event.

### Cost forecasting
`GET /jobs/{id}/forecast` returns:
- Burn rate ($/hr)
- ETA to completion
- Estimated final cost
- Budget breach probability (0-1 linear interpolation from 80%→100% of limit)

### Provider SLA tracker
5-minute rolling window per provider — records every availability sample, calculates uptime %, incident count, and assigns a grade (A≥99%, B≥95%, C≥90%, D<90%).

### Per-job efficiency report
`GET /jobs/{id}/report` returns a 0-100 efficiency score (50 pts price competitiveness + 50 pts GPU utilisation), GPU util stats (avg/peak/min/stddev), wasted capacity %, and a plain-English recommendation.

### Prometheus metrics
`GET /metrics` returns a Prometheus text/plain scrape payload (no auth, standard convention). Exposes job counts by status, total spend, avg GPU util, spot prices per provider, SLA%, and rate-limit usage per key.

### Webhook notifications
`POST /webhooks` registers a callback URL for job lifecycle events. When a job completes or is cancelled, the engine fires an authenticated HTTP POST to every matching webhook for that owner:
```json
{ "type": "job_complete", "job_id": "a1b2c3d4", "provider": "runpod-a100", "cost": 0.0412 }
```
Webhook delivery is non-blocking (asyncio background task). Each webhook records its last 50 delivery attempts with status codes. The `secret` field is forwarded as `X-Hook-Secret` for HMAC verification.

### Other
- **Job templates** — save/recall launch configs (provider, priority, budget)
- **Job clone** — `POST /jobs/{id}/clone` replays a job with the same settings
- **Paginated `GET /jobs`** — `?page=1&limit=20`, with `X-Total-Count`/`X-Total-Pages` response headers
- **Rate limiting** — 30 req/min per API key, sliding window; `X-RateLimit-Remaining` on every response
- **Request tracing** — `X-Request-ID` on every response (client-supplied or auto-generated UUID)
- **Structured JSON logging** — every action emits `{"ts":…,"level":…,"event":…}` to stdout
- **Multi-brand theming** — `/brand/voltgrid` or `/brand/partnera` applies colors + tagline via CSS custom properties
- **Light/dark mode** — toggle with `☀` button, preference persisted to localStorage
- **Keyboard shortcuts** — `L` launch · `1/2/3` priority · `Esc` cancel · `R` refresh · `F` search · `?` help overlay
- **CSV export** — download full job history as CSV

---

## API Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/providers` | ✅ | All providers with price, uptime, health score |
| `GET` | `/providers/{id}` | ✅ | Single provider |
| `GET` | `/providers/health` | ✅ | Composite health score (0-100) per provider |
| `GET` | `/providers/sla` | ✅ | 5-min rolling SLA stats for all providers |
| `GET` | `/providers/{id}/sla` | ✅ | SLA for one provider |
| `GET` | `/spot-prices` | ✅ | Current spot prices |
| `POST` | `/jobs` | ✅ | Launch job. `{}` = auto-pick; or pass `provider_id`, `priority`, `budget_limit`, `template_id` |
| `GET` | `/jobs` | ✅ | Paginated job list (scoped to API key) |
| `GET` | `/jobs/{id}` | ✅ | Job status, cost, GPU util |
| `DELETE` | `/jobs/{id}` | ✅ | Cancel a running job |
| `GET` | `/jobs/{id}/logs` | ✅ | Log lines |
| `GET` | `/jobs/{id}/forecast` | ✅ | Burn rate, ETA, breach probability |
| `GET` | `/jobs/{id}/report` | ✅ | Efficiency score + GPU util stats |
| `POST` | `/jobs/{id}/clone` | ✅ | Replay a job with the same config |
| `GET` | `/templates` | ✅ | List saved templates |
| `POST` | `/templates` | ✅ | Save a template |
| `GET` | `/templates/{id}` | ✅ | Get template |
| `DELETE` | `/templates/{id}` | ✅ | Delete template |
| `GET` | `/analytics` | ✅ | Aggregate spend + job counts |
| `GET` | `/admin/audit` | ✅ admin | Immutable audit log |
| `GET` | `/metrics` | ❌ | Prometheus scrape endpoint |
| `GET` | `/system/info` | ✅ | Version, WS subscriber count, provider stats |
| `GET` | `/brand/{name}` | ❌ | Brand config (colors, logo, tagline) |
| `POST` | `/webhooks` | ✅ | Register callback URL for job events |
| `GET` | `/webhooks` | ✅ | List webhooks (scoped to API key) |
| `GET` | `/webhooks/{id}` | ✅ | Get webhook + delivery log |
| `DELETE` | `/webhooks/{id}` | ✅ | Delete webhook |
| `WS` | `/ws/jobs/{id}/logs` | — | Per-job log + GPU util stream |
| `WS` | `/ws/events` | — | Global job state broadcast |
| `GET` | `/health` | ❌ | `{"status":"ok"}` |

---

## API Keys

| Key | Role | Notes |
|-----|------|-------|
| `demo-key-123` | demo-user | Standard access, pre-filled in UI |
| `admin-key-456` | admin-user | Unlocks `/admin/audit` |
| `test-key-789` | test-user | Standard access |
| `tenant-key-000` | tenant-user | Separate namespace for isolation testing |

All protected routes require `X-API-Key: <key>` header. Rate limit is 30 req/min per key.

---

## Project Structure

```
mini-compute-console/
├── backend/
│   ├── main.py           # FastAPI app — all 25 routes
│   ├── job_engine.py     # State machine, lifecycle, auto-reroute, budget check
│   ├── database.py       # SQLite CRUD (no ORM) + cold-start replay
│   ├── auth.py           # API key table + sliding-window rate limiter
│   ├── spot_prices.py    # Ornstein-Uhlenbeck price simulation
│   ├── health_score.py   # Composite provider scoring (uptime·50 + price·30 + spot·20)
│   ├── sla_tracker.py    # 5-min rolling availability window per provider
│   ├── forecast.py       # Burn rate, ETA, budget breach probability
│   ├── report.py         # Efficiency score + GPU util stats
│   ├── pubsub.py         # WebSocket fan-out hub
│   ├── metrics.py        # Prometheus text/plain scrape payload
│   ├── budget.py         # Auto-cancel guardrail
│   ├── templates.py      # Job template CRUD
│   ├── analytics.py      # Aggregate spend + usage stats
│   ├── audit_log.py      # Immutable action log
│   ├── webhooks.py       # Webhook registry + async delivery
│   ├── logger.py         # Structured JSON logging to stdout
│   ├── mock_data.py      # 8 GPU providers
│   └── requirements.txt
├── frontend/
│   ├── index.html        # Single-page app shell
│   ├── app.js            # All UI logic — no framework
│   ├── style.css         # CSS custom properties, dark + light themes
│   └── brands/           # JSON brand configs
├── tests/
│   ├── conftest.py       # TestClient fixtures + autouse reset
│   ├── test_api.py       # 64 integration tests
│   └── test_job_engine.py  # 11 unit tests
├── ARCHITECTURE.md       # System diagram + design decisions
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/ci.yml
```

---

## Design highlights

**State machine without background threads** — jobs advance via a pure function of `time.time() - started_at`. No threads, no scheduler. Cost, status, and log position are all derived on each request.

**SQLite with cold-start replay** — on startup, `_boot()` reloads all persisted jobs and marks stale `queued`/`running` entries as `complete` — the same pattern Kubernetes uses when a node restarts.

**Pub-sub with `asyncio.create_task`** — `broadcast_sync()` in the synchronous job engine fires an async fan-out by grabbing the running event loop's `create_task`. Avoids deprecated `get_event_loop()` and doesn't block.

**404 not 403 on cross-tenant access** — leaking job existence to another tenant is itself a security issue. Every tenant-scoped route returns 404 if the job belongs to a different owner.

**75 integration tests, isolated with `autouse` fixture** — `_jobs.clear()`, `_webhooks.clear()`, and `_rate_counters.clear()` run before and after every test, making test order irrelevant and eliminating state bleed across the full suite.

---

## Tech choices

| Choice | Why |
|--------|-----|
| FastAPI | Async, auto-generates OpenAPI docs, Pydantic v2 validation |
| SQLite (raw SQL) | Crash recovery without ORM overhead; demonstrates direct SQL |
| Vanilla JS | No build step; runs by opening a file; proves JS fundamentals |
| CSS custom properties | Full theming without a CSS-in-JS library |
| Ornstein-Uhlenbeck | Mean-reverting spot prices match real market behavior |
| Prometheus text format | Drop a Grafana stack in front and it works |
