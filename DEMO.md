# Demo Guide

A 3-minute walkthrough that shows every interesting system in action.

---

## Start the app

```bash
# Terminal 1 — backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && python3 -m http.server 3000
```

Open **http://localhost:3000** — the UI pre-fills `demo-key-123`.

Or with Docker:
```bash
docker-compose up
# backend :8000  ·  frontend :3000
```

---

## Demo flow (in order)

### 1. Watch the provider table update live
The spot prices tick every 15 seconds using an **Ornstein-Uhlenbeck** mean-reverting walk. Watch the `▲`/`▼`/`—` trend arrows change. The **Health** column is a composite score (uptime × 50 + price × 30 + spot × 20). The **SLA** column shows the 5-minute rolling availability grade.

### 2. Launch a job with a budget cap
Enter `0.10` in the **Budget $** field, select **Normal** priority, click **⚡ Auto Pick & Launch**.

- The engine picks the **cheapest spot price** among available providers with uptime ≥ 98%
- The job panel appears on the right with a live cost ticker (`$0.0001`, `$0.0002`, …)
- **Live Logs ● WS** — logs are pushed over WebSocket (not polled)
- The **Budget** bar fills as spend approaches the cap

### 3. Watch the Cost Forecast panel
Scroll down the right panel while the job is running. You'll see:
- Estimated final cost and ETA
- Burn rate ($/hr)
- Spot vs base price savings
- Budget breach probability bar — turns orange above 40%, red above 80%

### 4. Let the job complete
After ~90 seconds the status flips to **COMPLETE**. The **Efficiency Report** panel appears:
- Score 0–100 (50 pts price competitiveness + 50 pts GPU utilisation)
- A/B/C/D grade
- Avg GPU util, peak util, wasted capacity %
- Plain-English recommendation (e.g. "A cheaper provider was available — try normal priority")

### 5. Clone and replay
In the job card (or history table row), click the row to reload it, then call:
```
POST /jobs/{id}/clone
```
The engine replays the same provider and priority — useful for benchmarking reproducibility.

### 6. Switch to admin key to see the audit log
Change the API key input to `admin-key-456`. The **Audit Log** panel appears in the sidebar showing every job launch with timestamp, user, and provider.

### 7. Try the keyboard shortcuts
Press `?` to open the shortcut overlay:
- `L` — auto-launch a job
- `1` / `2` / `3` — switch priority (High / Normal / Low)
- `Esc` — cancel the active job
- `R` — refresh providers
- `F` — focus job search

### 8. Toggle light mode
Click `☀` in the top-right corner. All CSS custom properties swap via a `body.light` class toggle — no page reload, preference saved to localStorage.

### 9. Check the Prometheus scrape endpoint
```bash
curl http://localhost:8000/metrics
```
Returns a valid Prometheus text/plain payload. Drop a Grafana stack in front and you have a real dashboard.

### 10. Multi-tenant isolation
```bash
# Launch a job as tenant-user
curl -X POST http://localhost:8000/jobs \
  -H "X-API-Key: tenant-key-000" \
  -H "Content-Type: application/json" \
  -d '{}'

# Try to read it as admin-user — returns 404, not 403
JOB_ID=<id from above>
curl http://localhost:8000/jobs/$JOB_ID \
  -H "X-API-Key: admin-key-456"
# → {"detail":"Not found"}
```

The 404 (not 403) prevents leaking job existence to other tenants.

---

## API explorer

FastAPI auto-generates interactive docs at **http://localhost:8000/docs** — every endpoint is documented with request/response schemas, try-it-out support, and example payloads.

---

## Run the tests

```bash
pip install pytest httpx
pytest tests/ -v
# 64 tests · ~0.2s · zero disk side effects (uses temp DB)
```
