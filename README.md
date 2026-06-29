# Mini Compute Console

A full-stack GPU marketplace dashboard demonstrating job routing, live status tracking, multi-brand theming, and API security — built as a portfolio project modeled after the Tatari compute platform.

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs auto-generated at: http://localhost:8000/docs

### Frontend

Open `frontend/index.html` in a browser (no build step needed), or serve it locally:

```bash
cd frontend
python3 -m http.server 3000
# then visit http://localhost:3000
```

## API Keys

| Key | User | Notes |
|-----|------|-------|
| `demo-key-123` | demo-user | Standard access |
| `admin-key-456` | admin-user | Enables audit log view in the UI |
| `test-key-789` | test-user | Standard access |

Pass as header: `X-API-Key: demo-key-123`

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/providers` | ✅ | List all GPU providers with price, uptime, status |
| POST | `/jobs` | ✅ | Launch a job. Body: `{"provider_id": "rp-us-east-1"}` or `{}` for auto-pick |
| GET | `/jobs/{job_id}` | ✅ | Get job status, elapsed cost |
| GET | `/jobs/{job_id}/logs` | ✅ | Get simulated training logs |
| GET | `/brand/{brand_name}` | ❌ | Get brand config (colors, logo, name) |
| GET | `/admin/audit` | ✅ admin | Full audit log of all job launches |

## Features

### Smart Routing ("Tatari Engine")
Auto-pick filters to `status == available` and `uptime_pct >= 98`, then picks the lowest `price_per_hour`. Mirrors the routing logic described in Tatari's platform architecture.

### Live Job Simulation
Jobs transition: `queued → running → complete` over ~90 seconds. Cost counter and log stream update on every poll — no background workers needed, all state derived from `started_at` timestamp.

### Multi-Brand Theming
Visit `index.html?brand=tatari` or `index.html?brand=partnera`. Brand config (colors, logo, tagline) is fetched from `/brand/{name}` and applied via CSS custom properties — zero page reload, zero code change.

### Security Layer
- **API key auth**: checked on every protected route, 401 on missing/invalid key
- **Rate limiting**: 30 requests/minute per key, in-memory sliding window, no library dependency
- **Audit log**: every job launch records `{timestamp, user, provider_id, job_id}`, viewable at `/admin/audit` with admin key

## Project Structure

```
mini-compute-console/
├── backend/
│   ├── main.py          # FastAPI app, all routes
│   ├── mock_data.py     # 10 mock GPU providers across RunPod, Vast.ai, Colo
│   ├── job_engine.py    # Job state machine + log simulation
│   ├── auth.py          # API key check + sliding-window rate limiter
│   ├── audit_log.py     # In-memory audit trail
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── brands/
│       ├── tatari.json
│       └── partnera.json
└── README.md
```

## How it maps to the job posting

| Requirement | Implementation |
|-------------|----------------|
| "Build the console" | Provider table with launch flow, live status panel |
| "Make it brandable" | `?brand=` toggle, `/brand/{name}` endpoint, CSS vars |
| "Connect frontend to APIs" | Vanilla JS polling FastAPI, no framework overhead |
| "Live cost and usage" | Running cost computed from `elapsed_hours × price/hr` on every poll |
| "Job logs" | Simulated log stream, auto-scrolling log box |
| "Smart routing" | Auto-pick cheapest ≥98% uptime provider |
| "Security" | API key auth, rate limiting, audit log |
