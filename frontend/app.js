// Allow overriding via ?api=https://your-backend.railway.app in the URL
const _apiParam = new URLSearchParams(window.location.search).get("api");
const API_BASE  = _apiParam || (window.location.hostname === "localhost" ? "http://localhost:8000" : `${window.location.protocol}//${window.location.hostname}:8000`);
const WS_BASE   = API_BASE.replace(/^http/, "ws");
const JOB_DURATION_SECONDS = 90;

let currentJobId = null;
let activeSocket  = null;
let apiKey = "demo-key-123";
let _slaCache = {};

// ── Brand ─────────────────────────────────────────────────────────────────────

async function loadBrand(brandName) {
  try {
    const res = await fetch(`${API_BASE}/brand/${brandName}`);
    if (!res.ok) return;
    const b = await res.json();
    const r = document.documentElement.style;
    r.setProperty("--primary", b.primary_color);
    r.setProperty("--accent",  b.accent_color);
    r.setProperty("--bg",      b.bg_color);
    r.setProperty("--card",    b.card_color);
    r.setProperty("--text",    b.text_color);
    r.setProperty("--muted",   b.muted_color);
    document.getElementById("logo-text").textContent    = b.logo_text;
    document.getElementById("tagline-text").textContent = b.tagline;
    document.title = b.display_name;
    document.querySelectorAll(".brand-btn").forEach(btn =>
      btn.classList.toggle("active", btn.dataset.brand === brandName));
    const url = new URL(window.location);
    url.searchParams.set("brand", brandName);
    window.history.replaceState({}, "", url);
  } catch (e) { console.error("Brand load failed:", e); }
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const key = document.getElementById("api-key-input").value.trim() || apiKey;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "X-API-Key": key, "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── Providers + Spot Prices + SLA ─────────────────────────────────────────────

let _spotCache   = {};
let _healthCache = {};

async function loadProviders() {
  try {
    const [providers, spots, health, slas] = await Promise.all([
      apiFetch("/providers"),
      apiFetch("/spot-prices"),
      apiFetch("/providers/health"),
      apiFetch("/providers/sla"),
    ]);
    _spotCache   = Object.fromEntries(spots.map(s => [s.provider_id, s]));
    _healthCache = health;
    _slaCache    = slas;
    renderProviders(providers);
  } catch (e) { showToast(`Failed to load providers: ${e.message}`, "error"); }
}

function renderProviders(providers) {
  const tbody = document.getElementById("provider-tbody");
  tbody.innerHTML = "";
  providers.forEach(p => {
    const uptimeClass = p.uptime_pct >= 99 ? "uptime-high" : p.uptime_pct >= 98 ? "uptime-med" : "uptime-low";
    const dotClass    = p.status === "available" ? "dot-available" : "dot-busy";
    const available   = p.status === "available";
    const spot        = _spotCache[p.id];
    const spotPrice   = spot ? spot.spot_price : p.price_per_hour;
    const trend       = spot ? spot.trend : "flat";
    const trendIcon   = trend === "up" ? "▲" : trend === "down" ? "▼" : "—";
    const trendClass  = trend === "up" ? "trend-up" : trend === "down" ? "trend-down" : "trend-flat";
    const hs          = _healthCache[p.id];
    const grade       = hs ? hs.grade : "—";
    const gradeClass  = { A: "grade-a", B: "grade-b", C: "grade-c", D: "grade-d" }[grade] || "";
    const score       = hs ? hs.composite : "—";
    const sla         = _slaCache[p.id];
    const slaPct      = sla && sla.sla_pct != null ? `${sla.sla_pct.toFixed(1)}%` : "—";
    const slaGrade    = sla ? sla.grade : "—";
    const slaClass    = { A: "grade-a", B: "grade-b", C: "grade-c", D: "grade-d" }[slaGrade] || "";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><div class="provider-name">${p.name}</div></td>
      <td><span class="gpu-badge">${p.gpu_type}</span></td>
      <td class="muted-text">${p.region}</td>
      <td class="price muted-text">$${p.price_per_hour.toFixed(2)}<span class="price-unit">/hr</span></td>
      <td class="price">
        $${spotPrice.toFixed(2)}<span class="price-unit">/hr</span>
        <span class="trend-badge ${trendClass}">${trendIcon}</span>
      </td>
      <td class="uptime ${uptimeClass}">${p.uptime_pct}%</td>
      <td>
        <span class="health-grade ${gradeClass}" title="Score: ${score}">${grade}</span>
        <span class="muted-text" style="font-size:10px"> ${score}</span>
      </td>
      <td>
        <span class="health-grade ${slaClass}" title="5-min SLA: ${slaPct}">${slaGrade}</span>
        <span class="muted-text" style="font-size:10px"> ${slaPct}</span>
      </td>
      <td><span class="status-dot ${dotClass}"></span>${p.status}</td>
      <td>
        <button class="btn btn-primary btn-sm" ${available ? "" : "disabled"}
          onclick="launchJob('${p.id}')">Launch</button>
      </td>`;
    tbody.appendChild(tr);
  });
}

// ── Launch ────────────────────────────────────────────────────────────────────

function getSelectedPriority() {
  return document.querySelector('input[name="priority"]:checked')?.value || "normal";
}

async function launchJob(providerId, templateId) {
  const priority   = getSelectedPriority();
  const budgetRaw  = document.getElementById("budget-input")?.value;
  const budgetLimit = budgetRaw ? parseFloat(budgetRaw) : null;
  const body = {
    priority,
    ...(providerId  ? { provider_id: providerId }  : {}),
    ...(templateId  ? { template_id: templateId }  : {}),
    ...(budgetLimit ? { budget_limit: budgetLimit } : {}),
  };
  try {
    const job = await apiFetch("/jobs", { method: "POST", body: JSON.stringify(body) });
    currentJobId = job.job_id;
    showToast(`Job ${job.job_id} launched on ${job.provider_name}`, "success");
    renderJobCard(job, []);
    openWebSocket(job.job_id);
    refreshHistory();
    refreshAnalytics();
    refreshAuditLog();
    scheduleForecastPoll(job.job_id);
  } catch (e) { showToast(`Launch failed: ${e.message}`, "error"); }
}

// ── Cancel ────────────────────────────────────────────────────────────────────

async function cancelJob(jobId) {
  try {
    const job = await apiFetch(`/jobs/${jobId}`, { method: "DELETE" });
    showToast(`Job ${jobId} cancelled`, "");
    renderJobCard(job, job._logs || []);
    if (activeSocket) { activeSocket.close(); activeSocket = null; }
    document.getElementById("forecast-card").style.display = "none";
    refreshHistory();
    refreshAnalytics();
  } catch (e) { showToast(`Cancel failed: ${e.message}`, "error"); }
}

// ── WebSocket log stream ──────────────────────────────────────────────────────

function openWebSocket(jobId) {
  if (activeSocket) { activeSocket.close(); activeSocket = null; }

  const ws = new WebSocket(`${WS_BASE}/ws/jobs/${jobId}/logs`);
  activeSocket = ws;

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.line) appendLogLine(msg.line);

    if (msg.util !== undefined) {
      updateGpuSparkline(msg.gpu_samples || [], msg.util);
      if (msg.cost !== undefined) {
        const el = document.getElementById("cost-ticker");
        if (el) el.textContent = `$${msg.cost.toFixed(4)}`;
      }
    }

    if (msg.status) {
      apiFetch(`/jobs/${jobId}`).then(job => {
        renderJobCard(job, null);
        refreshHistory();
        refreshAnalytics();
        document.getElementById("forecast-card").style.display = "none";
      });
      if (msg.retry_count > 0)
        showToast(`Job re-routed ${msg.retry_count}× due to provider availability`, "");
    }

    if (msg.error) {
      showToast(`Stream error: ${msg.error}`, "error");
      ws.close();
    }
  };

  ws.onerror = () => showToast("WebSocket connection lost", "error");
}

function appendLogLine(line) {
  const box = document.getElementById("log-box");
  if (!box) return;
  const empty = box.querySelector(".log-empty");
  if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = "log-line";
  div.textContent = line;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

// ── GPU sparkline ─────────────────────────────────────────────────────────────

function updateGpuSparkline(samples, currentUtil) {
  const el     = document.getElementById("gpu-sparkline");
  const utilEl = document.getElementById("gpu-util-pct");
  if (!el) return;
  if (utilEl) utilEl.textContent = `${currentUtil}%`;
  if (!samples.length) return;

  const W = 80, H = 24, max = 100, min = 80;
  const pts = samples.map((v, i) => {
    const x = (i / (samples.length - 1 || 1)) * W;
    const y = H - ((v - min) / (max - min)) * H;
    return `${x},${y}`;
  }).join(" ");

  el.innerHTML = `<polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`;
}

// ── Rate limit bar ────────────────────────────────────────────────────────────

async function refreshRateLimit() {
  try {
    const info = await apiFetch("/rate-limit");
    const pct  = (info.remaining / info.limit) * 100;
    const el   = document.getElementById("rate-remaining");
    const bar  = document.getElementById("rate-bar");
    if (el)  el.textContent    = info.remaining;
    if (bar) bar.style.width   = `${pct}%`;
    if (bar) bar.style.background = pct > 50 ? "var(--success)" : pct > 20 ? "var(--warn)" : "var(--danger)";
  } catch { /* silent */ }
}

// ── CSV export ────────────────────────────────────────────────────────────────

async function exportCSV() {
  try {
    const jobs = await apiFetch("/jobs");
    if (!jobs.length) { showToast("No jobs to export", ""); return; }
    const cols = ["job_id","provider_id","provider_name","gpu_type","region","priority","status","price_per_hour","cost_so_far","projected_cost","budget_limit","retry_count","owner","started_at"];
    const rows = jobs.map(j => cols.map(h => {
      const v = j[h] ?? "";
      return typeof v === "string" && v.includes(",") ? `"${v}"` : v;
    }).join(","));
    const csv  = [cols.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `voltgrid-jobs-${Date.now()}.csv`;
    a.click(); URL.revokeObjectURL(url);
    showToast(`Exported ${jobs.length} jobs`, "success");
  } catch (e) { showToast(`Export failed: ${e.message}`, "error"); }
}

// ── Job card ──────────────────────────────────────────────────────────────────

function renderJobCard(job, logs) {
  const panel      = document.getElementById("job-panel");
  const elapsed    = job.cost_so_far / job.price_per_hour * 3600;
  const progress   = Math.min((elapsed / JOB_DURATION_SECONDS) * 100, 100);
  const badgeClass = { queued: "badge-queued", running: "badge-running", complete: "badge-complete", cancelled: "badge-cancelled" }[job.status] || "badge-queued";
  const cancelBtn  = (job.status === "queued" || job.status === "running")
    ? `<button class="btn btn-danger btn-sm" onclick="cancelJob('${job.job_id}')">✕ Cancel</button>`
    : "";

  panel.innerHTML = `
    <div class="job-header">
      <div>
        <div class="job-id">JOB-${job.job_id.toUpperCase()}</div>
        <div class="job-provider">${job.provider_name}</div>
        <div class="job-detail">${job.gpu_type} · ${job.region}</div>
        <div style="margin-top:4px;display:flex;align-items:center;gap:6px">
          <span class="priority-chip ${job.priority}">${job.priority}</span>
          <span class="owner-chip">👤 ${job.owner}</span>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:8px">
        <span class="job-status-badge ${badgeClass}">${job.status}</span>
        ${cancelBtn}
      </div>
    </div>

    <div class="cost-display">
      <div>
        <div class="cost-label">Running Cost</div>
        <div class="cost-value" id="cost-ticker">$${job.cost_so_far.toFixed(4)}</div>
      </div>
      <div style="text-align:right">
        <div class="cost-rate">$${job.price_per_hour.toFixed(2)}/hr spot</div>
        ${job.projected_cost != null
          ? `<div class="projected-cost">~$${job.projected_cost.toFixed(4)} projected</div>`
          : ""}
      </div>
    </div>

    <div class="progress-bar-wrap">
      <div class="progress-bar-fill" style="width:${progress}%"></div>
    </div>

    ${job.budget_limit != null ? (() => {
      const pct       = job.budget_pct_used ?? 0;
      const fillClass = pct >= 90 ? "danger" : pct >= 70 ? "warn" : "";
      return `<div class="budget-bar-wrap">
        <div class="budget-bar-label">
          <span>Budget</span>
          <span>$${job.cost_so_far.toFixed(4)} / $${job.budget_limit.toFixed(2)} (${pct.toFixed(1)}%)</span>
        </div>
        <div class="budget-bar-bg">
          <div class="budget-bar-fill ${fillClass}" style="width:${pct}%"></div>
        </div>
      </div>`;
    })() : ""}

    ${job.rerouted_from ? `<div class="reroute-notice">↪ Re-routed from <span class="mono">${job.rerouted_from}</span> (${job.retry_count}× retry)</div>` : ""}

    ${job.status === "running" ? `
    <div class="gpu-util-row">
      <span class="gpu-util-label">GPU Util</span>
      <svg class="sparkline" id="gpu-sparkline" viewBox="0 0 80 24" preserveAspectRatio="none"></svg>
      <span class="gpu-util-pct" id="gpu-util-pct">${job.gpu_util || 0}%</span>
    </div>` : ""}

    <div class="section-title" style="margin-top:16px">
      Live Logs
      <span class="ws-badge" id="ws-badge">● WS</span>
    </div>
    <div class="log-box" id="log-box">
      ${logs === null
        ? ""
        : logs.length === 0
          ? '<span class="log-empty">Waiting for logs…</span>'
          : logs.map(l => `<div class="log-line">${escapeHtml(l)}</div>`).join("")
      }
    </div>`;

  if (job.status === "running") startCostTicker(job.price_per_hour, job.cost_so_far);
  if (job.status === "complete") loadJobReport(job.job_id);
  else document.getElementById("report-card").style.display = "none";
}

let _tickerInterval = null;
function startCostTicker(pricePerHour, startCost) {
  if (_tickerInterval) clearInterval(_tickerInterval);
  const startTime = Date.now();
  _tickerInterval = setInterval(() => {
    const el = document.getElementById("cost-ticker");
    if (!el) { clearInterval(_tickerInterval); return; }
    const secs = (Date.now() - startTime) / 1000;
    el.textContent = `$${(startCost + (secs / 3600) * pricePerHour).toFixed(4)}`;
  }, 500);
}

// ── Efficiency report panel ───────────────────────────────────────────────────

async function loadJobReport(jobId) {
  try {
    const r    = await apiFetch(`/jobs/${jobId}/report`);
    const card = document.getElementById("report-card");
    const body = document.getElementById("report-body");
    card.style.display = "";

    const gradeColor = { A: "var(--success)", B: "var(--accent)", C: "var(--warn)", D: "var(--danger)" };
    const gc = gradeColor[r.efficiency_grade] || "var(--muted)";
    const util = r.gpu_util || {};

    body.innerHTML = `
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
        <div style="font-size:42px;font-weight:800;color:${gc};font-family:'JetBrains Mono',monospace;line-height:1">
          ${r.efficiency_score}
        </div>
        <div>
          <div style="font-size:22px;font-weight:700;color:${gc}">${r.efficiency_grade}</div>
          <div style="font-size:11px;color:var(--muted)">Efficiency score / 100</div>
        </div>
      </div>
      <div class="forecast-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px">
        <div class="forecast-stat">
          <div class="forecast-val">${util.avg != null ? util.avg.toFixed(1) : "—"}%</div>
          <div class="forecast-lbl">Avg GPU Util</div>
        </div>
        <div class="forecast-stat">
          <div class="forecast-val">${util.peak != null ? util.peak.toFixed(1) : "—"}%</div>
          <div class="forecast-lbl">Peak Util</div>
        </div>
        <div class="forecast-stat">
          <div class="forecast-val">${r.wasted_capacity_pct != null ? r.wasted_capacity_pct.toFixed(1) : "—"}%</div>
          <div class="forecast-lbl">Wasted Capacity</div>
        </div>
      </div>
      <div style="font-size:11px;color:var(--muted);padding:8px 10px;background:rgba(255,255,255,0.04);border-radius:6px;border-left:2px solid ${gc}">
        ${escapeHtml(r.recommendation || "No recommendation.")}
      </div>`;
  } catch { /* job may not be done yet */ }
}

// ── Forecast panel ────────────────────────────────────────────────────────────

let _forecastInterval = null;

function scheduleForecastPoll(jobId) {
  if (_forecastInterval) clearInterval(_forecastInterval);
  refreshForecast(jobId);
  _forecastInterval = setInterval(async () => {
    const job = await apiFetch(`/jobs/${jobId}`).catch(() => null);
    if (!job || job.status === "complete" || job.status === "cancelled") {
      clearInterval(_forecastInterval);
      document.getElementById("forecast-card").style.display = "none";
      return;
    }
    refreshForecast(jobId);
  }, 5000);
}

async function refreshForecast(jobId) {
  try {
    const f   = await apiFetch(`/jobs/${jobId}/forecast`);
    const card = document.getElementById("forecast-card");
    const body = document.getElementById("forecast-body");
    card.style.display = "";

    const breachPct  = (f.budget_breach_prob * 100).toFixed(0);
    const breachColor = f.budget_breach_prob >= 0.8 ? "var(--danger)" : f.budget_breach_prob >= 0.4 ? "var(--warn)" : "var(--success)";
    const etaMins    = (f.eta_seconds / 60).toFixed(1);
    const savings    = f.savings_vs_base;

    body.innerHTML = `
      <div class="forecast-grid">
        <div class="forecast-stat">
          <div class="forecast-val">$${f.estimated_final_cost.toFixed(4)}</div>
          <div class="forecast-lbl">Estimated Final</div>
        </div>
        <div class="forecast-stat">
          <div class="forecast-val">${etaMins}m</div>
          <div class="forecast-lbl">ETA</div>
        </div>
        <div class="forecast-stat">
          <div class="forecast-val">$${f.burn_rate_per_hour.toFixed(2)}/hr</div>
          <div class="forecast-lbl">Burn Rate</div>
        </div>
        <div class="forecast-stat">
          <div class="forecast-val" style="color:${savings >= 0 ? 'var(--success)' : 'var(--danger)'}">
            ${savings >= 0 ? "-" : "+"}$${Math.abs(savings).toFixed(4)}
          </div>
          <div class="forecast-lbl">vs Base Price</div>
        </div>
      </div>
      ${f.budget_limit ? `
      <div class="forecast-breach">
        <div class="forecast-breach-label">
          <span>Budget breach risk</span>
          <span style="color:${breachColor};font-weight:700">${breachPct}%</span>
        </div>
        <div class="budget-bar-bg">
          <div class="budget-bar-fill ${f.budget_breach_prob >= 0.8 ? 'danger' : f.budget_breach_prob >= 0.4 ? 'warn' : ''}"
               style="width:${breachPct}%"></div>
        </div>
        ${f.over_budget_by ? `<div style="font-size:10px;color:var(--danger);margin-top:4px">Over by $${f.over_budget_by.toFixed(4)} if run to completion</div>` : ""}
      </div>` : ""}`;
  } catch { /* job may have ended */ }
}

// ── Job history with filter ───────────────────────────────────────────────────

let _allJobs = [];

async function refreshHistory() {
  try {
    _allJobs = await apiFetch("/jobs");
    applyHistoryFilter();
  } catch { /* silent */ }
}

function applyHistoryFilter() {
  const search   = document.getElementById("job-search")?.value.toLowerCase() || "";
  const status   = document.getElementById("filter-status")?.value || "";
  const priority = document.getElementById("filter-priority")?.value || "";
  const countEl  = document.getElementById("history-count");

  let filtered = [..._allJobs].reverse();
  if (search)   filtered = filtered.filter(j => j.provider_name.toLowerCase().includes(search) || j.job_id.includes(search));
  if (status)   filtered = filtered.filter(j => j.status === status);
  if (priority) filtered = filtered.filter(j => j.priority === priority);

  if (countEl) {
    countEl.textContent = filtered.length < _allJobs.length
      ? `Showing ${filtered.length} of ${_allJobs.length} jobs`
      : "";
  }

  renderHistory(filtered);
}

function renderHistory(jobs) {
  const tbody = document.getElementById("history-tbody");
  if (!jobs.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="table-empty">No jobs match your filter.</td></tr>';
    return;
  }
  tbody.innerHTML = jobs.map(j => {
    const badgeClass = { queued: "badge-queued", running: "badge-running", complete: "badge-complete", cancelled: "badge-cancelled" }[j.status] || "badge-queued";
    const cancelBtn  = (j.status === "queued" || j.status === "running")
      ? `<button class="btn btn-danger btn-sm" onclick="cancelJob('${j.job_id}')">✕</button>`
      : "—";
    const budgetCol  = j.budget_limit ? `<span class="budget-chip">$${j.budget_limit.toFixed(2)}</span>` : "";
    return `<tr class="${j.job_id === currentJobId ? 'row-active' : ''}" onclick="selectJobFromHistory('${j.job_id}')" style="cursor:pointer">
      <td><span class="mono">${j.job_id}</span></td>
      <td>${j.provider_name}${budgetCol}</td>
      <td><span class="gpu-badge">${j.gpu_type}</span></td>
      <td><span class="priority-chip ${j.priority}">${j.priority}</span></td>
      <td><span class="job-status-badge ${badgeClass}">${j.status}</span></td>
      <td class="price">$${j.cost_so_far.toFixed(4)}</td>
      <td class="muted-text" style="text-align:center">${j.retry_count || 0}</td>
      <td onclick="event.stopPropagation()">${cancelBtn}</td>
    </tr>`;
  }).join("");
}

async function selectJobFromHistory(jobId) {
  try {
    const job = await apiFetch(`/jobs/${jobId}`);
    currentJobId = jobId;
    renderJobCard(job, null);
    applyHistoryFilter();
    if (job.status === "running") {
      openWebSocket(jobId);
      scheduleForecastPoll(jobId);
    } else {
      document.getElementById("forecast-card").style.display = "none";
    }
    if (job.status === "complete") loadJobReport(jobId);
    const logs = await apiFetch(`/jobs/${jobId}/logs`);
    const box  = document.getElementById("log-box");
    if (box) box.innerHTML = logs.logs.map(l => `<div class="log-line">${escapeHtml(l)}</div>`).join("") || '<span class="log-empty">No logs.</span>';
  } catch (e) { showToast(`Could not load job: ${e.message}`, "error"); }
}

// ── Analytics ─────────────────────────────────────────────────────────────────

async function refreshAnalytics() {
  try {
    const a = await apiFetch("/analytics");
    document.getElementById("m-total-jobs").textContent   = a.total_jobs;
    document.getElementById("m-running").textContent      = a.running_jobs;
    document.getElementById("m-completed").textContent    = a.completed_jobs;
    document.getElementById("m-spend").textContent        = `$${a.total_spend.toFixed(4)}`;
    document.getElementById("m-avg-cost").textContent     = `$${a.avg_cost_per_job.toFixed(4)}`;
    document.getElementById("m-top-provider").textContent =
      a.most_used_provider ? a.most_used_provider.split("·")[0].trim() : "—";
    renderSpendChart(a.provider_breakdown);
  } catch { /* silent */ }
}

// ── Spend bar chart ───────────────────────────────────────────────────────────

function renderSpendChart(breakdown) {
  const container = document.getElementById("spend-chart");
  const entries   = Object.entries(breakdown).sort((a, b) => b[1].total_spend - a[1].total_spend);
  if (!entries.length) {
    container.innerHTML = '<span class="chart-empty">Launch jobs to see spend breakdown.</span>';
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v.total_spend), 0.0001);
  container.innerHTML = entries.map(([pid, stats]) => {
    const pct   = (stats.total_spend / max) * 100;
    const label = pid.split("-").slice(0, 2).join("-");
    return `<div class="chart-row">
      <div class="chart-label" title="${pid}">${label}</div>
      <div class="chart-bar-wrap"><div class="chart-bar" style="width:${pct}%"></div></div>
      <div class="chart-value">$${stats.total_spend.toFixed(4)}</div>
    </div>`;
  }).join("");
}

// ── Audit log ─────────────────────────────────────────────────────────────────

async function refreshAuditLog() {
  const key = document.getElementById("api-key-input").value.trim() || apiKey;
  if (key !== "admin-key-456") {
    document.getElementById("audit-card").style.display = "none";
    return;
  }
  try {
    const entries = await apiFetch("/admin/audit");
    const card    = document.getElementById("audit-card");
    card.style.display = "";
    const list = document.getElementById("audit-list");
    if (!entries.length) {
      list.innerHTML = '<span class="audit-empty">No activity yet.</span>';
      return;
    }
    list.innerHTML = entries.slice(0, 10).map(e => `
      <div class="audit-item">
        <div class="audit-item-top">
          <span class="audit-job-id">${e.job_id}</span>
          <span class="audit-action audit-action-${e.action}">${e.action}</span>
          <span class="audit-ts">${new Date(e.timestamp).toLocaleTimeString()}</span>
        </div>
        <div class="audit-detail"><span class="audit-user">${e.user}</span> → ${e.provider_id}</div>
      </div>`).join("");
  } catch { document.getElementById("audit-card").style.display = "none"; }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let _toastTimer = null;
function showToast(msg, type = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className   = `show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { t.className = ""; }, 3500);
}

// ── Templates ─────────────────────────────────────────────────────────────────

async function loadTemplates() {
  try { renderTemplates(await apiFetch("/templates")); } catch { /* silent */ }
}

function renderTemplates(templates) {
  const el = document.getElementById("templates-list");
  if (!templates.length) {
    el.innerHTML = '<span class="chart-empty">No templates saved yet.</span>';
    return;
  }
  el.innerHTML = templates.map(t => {
    const meta = [
      `<span class="priority-chip ${t.priority}">${t.priority}</span>`,
      t.budget_limit ? `$${t.budget_limit.toFixed(2)} cap` : "no cap",
      t.provider_id  ? t.provider_id : "auto-pick",
    ].join(" · ");
    return `<div class="template-row">
      <div class="template-info">
        <div class="template-name">${escapeHtml(t.name)}</div>
        <div class="template-meta">${meta}</div>
      </div>
      <div class="template-actions">
        <button class="btn-tpl-launch" onclick="launchJob(null,'${t.id}')">▶ Launch</button>
        <button class="btn-tpl-del" onclick="deleteTemplate('${t.id}')">✕</button>
      </div>
    </div>`;
  }).join("");
}

async function saveCurrentAsTemplate() {
  const name = prompt("Template name:");
  if (!name) return;
  const priority    = getSelectedPriority();
  const budgetRaw   = document.getElementById("budget-input")?.value;
  const budget_limit = budgetRaw ? parseFloat(budgetRaw) : null;
  try {
    await apiFetch("/templates", { method: "POST", body: JSON.stringify({ name, priority, budget_limit }) });
    showToast(`Template "${name}" saved`, "success");
    loadTemplates();
  } catch (e) { showToast(`Save failed: ${e.message}`, "error"); }
}

async function deleteTemplate(templateId) {
  try {
    const key = document.getElementById("api-key-input").value.trim() || apiKey;
    await fetch(`${API_BASE}/templates/${templateId}`, { method: "DELETE", headers: { "X-API-Key": key } });
    showToast("Template deleted", "");
    loadTemplates();
  } catch (e) { showToast(`Delete failed: ${e.message}`, "error"); }
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

function toggleKbOverlay(force) {
  const overlay = document.getElementById("kb-overlay");
  const show    = force !== undefined ? force : overlay.style.display === "none";
  overlay.style.display = show ? "flex" : "none";
}

function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    const tag = document.activeElement?.tagName.toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea") return;

    switch (e.key) {
      case "l": case "L":
        e.preventDefault();
        launchJob(null);
        showToast("Auto-launching job…", "");
        break;
      case "1":
        document.querySelector('input[name="priority"][value="high"]').checked = true;
        showToast("Priority → High", "");
        break;
      case "2":
        document.querySelector('input[name="priority"][value="normal"]').checked = true;
        showToast("Priority → Normal", "");
        break;
      case "3":
        document.querySelector('input[name="priority"][value="low"]').checked = true;
        showToast("Priority → Low", "");
        break;
      case "Escape":
        if (document.getElementById("kb-overlay").style.display !== "none") {
          toggleKbOverlay(false);
        } else if (currentJobId) {
          cancelJob(currentJobId);
        }
        break;
      case "r": case "R":
        e.preventDefault();
        loadProviders();
        showToast("Refreshing providers…", "");
        break;
      case "f": case "F": case "/":
        e.preventDefault();
        document.getElementById("job-search")?.focus();
        break;
      case "?":
        toggleKbOverlay();
        break;
    }
  });

  document.getElementById("kb-hint-btn").addEventListener("click", () => toggleKbOverlay());
  document.getElementById("kb-close").addEventListener("click", () => toggleKbOverlay(false));
  document.getElementById("kb-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) toggleKbOverlay(false);
  });
}

// ── Light / dark mode ────────────────────────────────────────────────────────

function initTheme() {
  const saved = localStorage.getItem("voltgrid-theme") || "dark";
  applyTheme(saved);
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = document.body.classList.contains("light") ? "dark" : "light";
    applyTheme(next);
    localStorage.setItem("voltgrid-theme", next);
  });
}

function applyTheme(theme) {
  document.body.classList.toggle("light", theme === "light");
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "light" ? "☾" : "☀";
}

// ── Global event stream (pub-sub WS) ─────────────────────────────────────────

function connectEventStream() {
  const ws = new WebSocket(`${WS_BASE}/ws/events`);
  const el  = document.getElementById("m-live-event");

  ws.onopen = () => {
    if (el) el.textContent = "Connected";
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "ping") return;

    const labels = {
      job_launched:  "Job launched",
      job_running:   "Job started",
      job_complete:  "Job complete",
      job_cancelled: "Job cancelled",
    };
    const label = labels[msg.type] || msg.type;
    const id    = msg.job_id ? ` · ${msg.job_id}` : "";
    if (el) el.textContent = `${label}${id}`;

    // Auto-refresh history + analytics on any state change
    if (msg.type !== "ping") {
      refreshHistory();
      refreshAnalytics();
    }
  };

  ws.onclose = () => {
    if (el) el.textContent = "Reconnecting…";
    setTimeout(connectEventStream, 3000);
  };

  ws.onerror = () => ws.close();
}

// ── Util ──────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  loadBrand(params.get("brand") || "voltgrid");

  document.querySelectorAll(".brand-btn").forEach(btn =>
    btn.addEventListener("click", () => loadBrand(btn.dataset.brand)));

  const keyInput = document.getElementById("api-key-input");
  keyInput.value = apiKey;
  keyInput.addEventListener("change", () => {
    loadProviders(); refreshHistory(); refreshAnalytics(); refreshAuditLog(); loadTemplates();
  });

  document.getElementById("auto-pick-btn").addEventListener("click", () => launchJob(null));
  document.getElementById("export-csv-btn").addEventListener("click", exportCSV);
  document.getElementById("save-template-btn").addEventListener("click", saveCurrentAsTemplate);

  // Filter inputs
  document.getElementById("job-search").addEventListener("input",    applyHistoryFilter);
  document.getElementById("filter-status").addEventListener("change", applyHistoryFilter);
  document.getElementById("filter-priority").addEventListener("change", applyHistoryFilter);

  initKeyboardShortcuts();
  initTheme();
  connectEventStream();

  loadProviders();
  refreshAnalytics();
  refreshHistory();
  refreshRateLimit();
  loadTemplates();

  setInterval(() => { loadProviders(); refreshAnalytics(); refreshHistory(); }, 15000);
  setInterval(refreshRateLimit, 5000);
});
