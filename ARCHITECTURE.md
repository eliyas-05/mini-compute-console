# Architecture — Mini Compute Console

A scaled-down GPU compute marketplace demonstrating real-time systems,
multi-tenant API design, and production-aware backend patterns.

---

## System Diagram

```
Browser (Vanilla JS)
  │
  ├── HTTP (REST)  ─────────────────────────► FastAPI (Python 3.12)
  │    GET /providers, /spot-prices, /jobs        │
  │    POST /jobs, /templates                     ├── Job Engine (state machine)
  │    GET /jobs/{id}/forecast                    │     ├── In-memory dict (_jobs)
  │    GET /jobs/{id}/report                      │     ├── SQLite (console.db)
  │    POST /jobs/{id}/clone                      │     └── Budget guardrail
  │    GET /metrics (Prometheus)                  │
  │                                               ├── Spot Price Simulator
  ├── WebSocket /ws/jobs/{id}/logs                │     └── Ornstein-Uhlenbeck walk
  │    ● Per-job log + GPU util stream            │
  │                                               ├── Health Scorer
  └── WebSocket /ws/events (pub-sub)              │     └── Composite 0-100 score
       ● Global broadcast — ALL tabs              │
         receive job state changes                ├── SLA Tracker
                                                  │     └── 5-min rolling window
                                                  │
                                                  ├── Auth + Rate Limiter
                                                  │     └── 30 req/min sliding window
                                                  │
                                                  └── Pub-Sub Hub (pubsub.py)
                                                        └── Fan-out to N WebSocket clients
```

---

## Key Design Decisions

### 1. In-memory state machine + SQLite persistence

Jobs live in `_jobs: dict[str, dict]` for zero-latency reads on every poll.
SQLite (`console.db`) is written on every state transition for crash recovery.
On startup, `_boot()` replays all persisted jobs and marks stale
`queued`/`running` jobs as `complete` — the same pattern used by real job
schedulers (Kubernetes marks Pods as Failed on node restart).

**Why not a full ORM?** Raw SQL (`sqlite3`) keeps the dependency footprint
minimal and demonstrates direct SQL knowledge, which matters more in an
interview than ORM fluency.

### 2. Ornstein-Uhlenbeck spot price simulation

Spot prices use a mean-reverting random walk rather than pure random noise:

```
price_t+1 = price_t + θ(μ - price_t) + σ·ε
θ = 0.15  (reversion speed)
σ = 0.04·base_price
```

This matches how real spot markets behave — prices drift but snap back
toward a long-run mean, creating realistic `▲`/`▼`/`—` trend signals.

### 3. Two WebSocket channels

| Channel | Path | Purpose |
|---------|------|---------|
| Per-job stream | `/ws/jobs/{id}/logs` | Log lines + GPU util for one job |
| Global broadcast | `/ws/events` | All job state changes, all tabs |

The global channel uses a pub-sub hub (`pubsub.py`): job_engine calls
`broadcast_sync()` on every transition, which fans out to every connected
WebSocket via `asyncio.create_task`. No polling, no missed updates.

### 4. Multi-tenant namespacing

Every job carries an `owner` field (the resolved username from the API key).
`GET /jobs`, `GET /jobs/{id}`, `DELETE`, forecast, report, and clone all
filter by owner — cross-tenant access returns 404, not 403, to avoid
leaking job existence.

### 5. Priority routing

| Priority | Strategy |
|----------|----------|
| `high` | Max uptime provider (never miss a deadline) |
| `normal` | Min spot price (cost-optimised) |
| `low` | Min base price (cheapest at list) |

If a provider goes busy while a job is queued, the engine auto-reroutes
up to 3 times and appends a log line — observable in the UI as a
`↪ Re-routed` notice with retry count.

### 6. Budget guardrails

`check_budget()` is called inside `get_job()` on every poll — no background
thread needed. When `cost_so_far >= budget_limit`, the job is cancelled,
a log line is appended, and a pub-sub event is broadcast. The frontend
shows a colour-coded budget bar and forecast breach probability.

### 7. Prometheus metrics

`GET /metrics` returns a Prometheus-compatible scrape payload (no auth
required, standard convention). Exposes: job counts by status, total spend,
average GPU utilisation, spot prices per provider, SLA%, and rate-limit
usage per key. Drop a Prometheus + Grafana stack in front and you have a
real monitoring setup.

---

## Request Lifecycle (Job Launch)

```
POST /jobs  →  verify_api_key()  →  rate limiter check
           →  template merge (if template_id)
           →  launch_job(owner=user)
                ├── _auto_pick_provider(priority)  or explicit provider
                ├── get_spot_price(provider_id)
                ├── build job dict, stamp owner
                ├── upsert_job() → SQLite
                ├── broadcast_sync("job_launched")  → all WS/events clients
                └── return job
           →  log_action() → audit log
           →  L.info() → structured JSON stdout
           →  _job_view(job) → HTTP 201
```

---

## File Map

```
backend/
  main.py          FastAPI app, all routes
  job_engine.py    State machine, job lifecycle, retry logic
  database.py      SQLite schema + CRUD (no ORM)
  auth.py          API key table, sliding-window rate limiter
  spot_prices.py   Ornstein-Uhlenbeck price simulation
  health_score.py  Composite provider scoring (uptime·50 + price·30 + spot·20)
  sla_tracker.py   5-minute rolling availability window per provider
  forecast.py      Burn rate, ETA, budget breach probability
  report.py        Efficiency score, GPU util stats, recommendation
  pubsub.py        WebSocket fan-out hub
  metrics.py       Prometheus text/plain scrape payload
  budget.py        Auto-cancel guardrail
  templates.py     Job template CRUD
  analytics.py     Aggregate spend + usage stats
  audit_log.py     Immutable action log
  webhooks.py      Webhook registry + async HTTP delivery
  logger.py        Structured JSON logging to stdout
  mock_data.py     8 GPU providers (RunPod, Vast.ai, Colo)

frontend/
  index.html       Single-page app shell
  app.js           All UI logic — no framework
  style.css        CSS custom properties, dark + light themes
  brands/          JSON brand configs for multi-tenant white-labelling

tests/
  conftest.py      TestClient fixtures, 4 API key constants
  test_api.py      64 integration tests
  test_job_engine.py  Unit tests for state machine
```

---

## What This Demonstrates

| Skill | Where |
|-------|-------|
| API design | RESTful routes, pagination headers, 404 vs 403 semantics |
| Real-time systems | Two WebSocket channels: point-to-point + pub-sub fan-out |
| Data persistence | SQLite with raw SQL, cold-start replay, upsert pattern |
| Auth + security | API key auth, sliding-window rate limiting, tenant isolation |
| Simulation | Ornstein-Uhlenbeck process for realistic market prices |
| Observability | Structured JSON logs, Prometheus metrics, SLA tracking |
| Event-driven integrations | Webhook registry with async delivery, delivery attempt log, secret signing |
| Testing | 75 tests, autouse fixtures, cross-tenant isolation assertions |
| Frontend | Vanilla JS, WebSocket client, live filtering, keyboard shortcuts |
| DevOps | Docker, docker-compose, GitHub Actions CI |
