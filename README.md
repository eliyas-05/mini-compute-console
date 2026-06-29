# Mini Compute Console

A scaled-down GPU compute marketplace — built as a portfolio project for a software engineering internship application.

Pick a provider, launch a job, and watch the cost tick up and logs stream in real time. No database, no build step, no framework overhead.

![screenshot placeholder](https://placehold.co/800x400/0D0D1A/6C5CE7?text=Mini+Compute+Console)

## Quick Start

**1. Start the backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Interactive API docs: http://localhost:8000/docs

**2. Open the frontend**
```bash
cd frontend
python3 -m http.server 3000
# visit http://localhost:3000
```

The UI ships with the demo API key pre-filled (`demo-key-123`) — just open it and click Launch.

## API Keys

| Key | Role | Notes |
|-----|------|-------|
| `demo-key-123` | demo-user | Standard access |
| `admin-key-456` | admin-user | Unlocks audit log panel in UI |
| `test-key-789` | test-user | Standard access |

All protected routes require `X-API-Key: <key>` header.

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/providers` | ✅ | List 8 GPU providers with price, uptime, region, status |
| `POST` | `/jobs` | ✅ | Launch a job. Pass `{"provider_id": "..."}` or `{}` to auto-pick |
| `GET` | `/jobs/{job_id}` | ✅ | Job status + running cost |
| `GET` | `/jobs/{job_id}/logs` | ✅ | Simulated training log stream |
| `GET` | `/brand/{name}` | ❌ | Brand config (colors, logo, tagline) |
| `GET` | `/admin/audit` | ✅ admin | Audit log of all job launches |

## Features

### Smart provider routing
`POST /jobs` with an empty body auto-selects the cheapest provider where `status == "available"` and `uptime_pct >= 98`. No random picks — deterministic, cheapest-first.

### Live job state machine
Jobs move through `queued → running → complete` over ~90 seconds. Cost and logs are derived from `started_at` on every poll — no background threads, no database.

### Simulated log streaming
While a job is running, each `GET /jobs/{id}/logs` poll appends a new realistic training log line (loss, GPU util, checkpoint saves, ETA). Auto-scrolls in the UI.

### Rate limiting
30 requests/minute per API key, in-memory sliding window — no third-party library.

### Audit log
Every job launch is recorded (`timestamp`, `user`, `provider_id`, `job_id`). Viewable at `/admin/audit` with the admin key, or in the UI sidebar.

### Multi-brand theming
`?brand=voltgrid` or `?brand=partnera` — brand colors, logo, and tagline are fetched from `/brand/{name}` and applied via CSS custom properties with no page reload.

## Project Structure

```
mini-compute-console/
├── backend/
│   ├── main.py          # FastAPI app — all routes
│   ├── mock_data.py     # 8 mock GPU providers (RunPod, Vast.ai, Colo)
│   ├── job_engine.py    # In-memory job state machine + log simulator
│   ├── auth.py          # API key auth + sliding-window rate limiter
│   ├── audit_log.py     # In-memory audit trail
│   └── requirements.txt
├── frontend/
│   ├── index.html       # Single-page UI, no framework
│   ├── style.css        # Dark theme with CSS custom properties
│   ├── app.js           # Vanilla JS — fetch, polling, brand switching
│   └── brands/
│       ├── voltgrid.json
│       └── partnera.json
└── README.md
```

## Tech choices

- **FastAPI** — async, auto-generates OpenAPI docs, Pydantic validation
- **No ORM / no database** — in-memory state keeps the focus on application logic
- **Vanilla JS** — no build step, no bundler; runs by opening a file
- **CSS custom properties** — theming without a CSS-in-JS library
