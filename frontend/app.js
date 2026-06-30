const API_BASE = "http://localhost:8000";
const WS_BASE  = "ws://localhost:8000";
const JOB_DURATION_SECONDS = 90;

let currentJobId = null;
let activeSocket  = null;
let apiKey = "demo-key-123";

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
    document.getElementById("logo-text").textContent   = b.logo_text;
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

// ── Providers + Spot Prices ───────────────────────────────────────────────────

let _spotCache   = {};
let _healthCache = {};

async function loadProviders() {
  try {
    const [providers, spots, health] = await Promise.all([
      apiFetch("/providers"),
      apiFetch("/spot-prices"),
      apiFetch("/providers/health"),
    ]);
    _spotCache   = Object.fromEntries(spots.map(s => [s.provider_id, s]));
    _healthCache = health;
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

async function launchJob(providerId) {
  const priority = getSelectedPriority();
  const body = { priority, ...(providerId ? { provider_id: providerId } : {}) };
  try {
    const job = await apiFetch("/jobs", { method: "POST", body: JSON.stringify(body) });
    currentJobId = job.job_id;
    showToast(`Job ${job.job_id} launched on ${job.provider_name}`, "success");
    renderJobCard(job, []);
    openWebSocket(job.job_id);
    refreshHistory();
    refreshAnalytics();
    refreshAuditLog();
  } catch (e) { showToast(`Launch failed: ${e.message}`, "error"); }
}

// ── Cancel ────────────────────────────────────────────────────────────────────

async function cancelJob(jobId) {
  try {
    const job = await apiFetch(`/jobs/${jobId}`, { method: "DELETE" });
    showToast(`Job ${jobId} cancelled`, "");
    renderJobCard(job, job._logs || []);
    if (activeSocket) { activeSocket.close(); activeSocket = null; }
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
  const el = document.getElementById("gpu-sparkline");
  const utilEl = document.getElementById("gpu-util-pct");
  if (!el) return;
  if (utilEl) utilEl.textContent = `${currentUtil}%`;
  if (!samples.length) return;

  const W = 80, H = 24;
  const max = 100, min = 80;
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
    const remaining = info.remaining;
    const pct = (remaining / info.limit) * 100;
    const el = document.getElementById("rate-remaining");
    const bar = document.getElementById("rate-bar");
    if (el) el.textContent = remaining;
    if (bar) {
      bar.style.width = `${pct}%`;
      bar.style.background = pct > 50 ? "var(--success)" : pct > 20 ? "var(--warn)" : "var(--danger)";
    }
  } catch { /* silent */ }
}

// ── CSV export ────────────────────────────────────────────────────────────────

async function exportCSV() {
  try {
    const jobs = await apiFetch("/jobs");
    if (!jobs.length) { showToast("No jobs to export", ""); return; }
    const headers = ["job_id","provider_id","provider_name","gpu_type","region","priority","status","price_per_hour","cost_so_far","projected_cost","retry_count","started_at"];
    const rows = jobs.map(j => headers.map(h => {
      const v = j[h] ?? "";
      return typeof v === "string" && v.includes(",") ? `"${v}"` : v;
    }).join(","));
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `jobs-${Date.now()}.csv`;
    a.click(); URL.revokeObjectURL(url);
    showToast(`Exported ${jobs.length} jobs`, "success");
  } catch (e) { showToast(`Export failed: ${e.message}`, "error"); }
}

// ── Job card ──────────────────────────────────────────────────────────────────

function renderJobCard(job, logs) {
  const panel = document.getElementById("job-panel");
  const elapsed = job.cost_so_far / job.price_per_hour * 3600;
  const progress = Math.min((elapsed / JOB_DURATION_SECONDS) * 100, 100);
  const badgeClass = { queued: "badge-queued", running: "badge-running", complete: "badge-complete", cancelled: "badge-cancelled" }[job.status] || "badge-queued";
  const cancelBtn = (job.status === "queued" || job.status === "running")
    ? `<button class="btn btn-danger btn-sm" onclick="cancelJob('${job.job_id}')">✕ Cancel</button>`
    : "";

  panel.innerHTML = `
    <div class="job-header">
      <div>
        <div class="job-id">JOB-${job.job_id.toUpperCase()}</div>
        <div class="job-provider">${job.provider_name}</div>
        <div class="job-detail">${job.gpu_type} · ${job.region}</div>
        <div style="margin-top:4px"><span class="priority-chip ${job.priority}">${job.priority}</span></div>
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

  // Tick the cost display locally while running
  if (job.status === "running") {
    startCostTicker(job.price_per_hour, job.cost_so_far);
  }
}

let _tickerInterval = null;
function startCostTicker(pricePerHour, startCost) {
  if (_tickerInterval) clearInterval(_tickerInterval);
  const startTime = Date.now();
  _tickerInterval = setInterval(() => {
    const el = document.getElementById("cost-ticker");
    if (!el) { clearInterval(_tickerInterval); return; }
    const secondsElapsed = (Date.now() - startTime) / 1000;
    const cost = startCost + (secondsElapsed / 3600) * pricePerHour;
    el.textContent = `$${cost.toFixed(4)}`;
  }, 500);
}

// ── Job history ───────────────────────────────────────────────────────────────

async function refreshHistory() {
  try {
    const jobs = await apiFetch("/jobs");
    renderHistory(jobs);
  } catch (e) { /* silent */ }
}

function renderHistory(jobs) {
  const tbody = document.getElementById("history-tbody");
  if (!jobs.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="table-empty">No jobs yet.</td></tr>';
    return;
  }
  tbody.innerHTML = [...jobs].reverse().map(j => {
    const badgeClass = { queued: "badge-queued", running: "badge-running", complete: "badge-complete", cancelled: "badge-cancelled" }[j.status] || "badge-queued";
    const cancelBtn = (j.status === "queued" || j.status === "running")
      ? `<button class="btn btn-danger btn-sm" onclick="cancelJob('${j.job_id}')">✕</button>`
      : "—";
    return `<tr>
      <td><span class="mono">${j.job_id}</span></td>
      <td>${j.provider_name}</td>
      <td><span class="gpu-badge">${j.gpu_type}</span></td>
      <td><span class="priority-chip ${j.priority}">${j.priority}</span></td>
      <td><span class="job-status-badge ${badgeClass}">${j.status}</span></td>
      <td class="price">$${j.cost_so_far.toFixed(4)}</td>
      <td class="muted-text" style="text-align:center">${j.retry_count || 0}</td>
      <td>${cancelBtn}</td>
    </tr>`;
  }).join("");
}

// ── Analytics ─────────────────────────────────────────────────────────────────

async function refreshAnalytics() {
  try {
    const a = await apiFetch("/analytics");
    document.getElementById("m-total-jobs").textContent  = a.total_jobs;
    document.getElementById("m-running").textContent     = a.running_jobs;
    document.getElementById("m-completed").textContent   = a.completed_jobs;
    document.getElementById("m-spend").textContent       = `$${a.total_spend.toFixed(4)}`;
    document.getElementById("m-avg-cost").textContent    = `$${a.avg_cost_per_job.toFixed(4)}`;
    document.getElementById("m-top-provider").textContent =
      a.most_used_provider ? a.most_used_provider.split("·")[0].trim() : "—";
    renderSpendChart(a.provider_breakdown);
  } catch (e) { /* silent */ }
}

// ── Spend bar chart ───────────────────────────────────────────────────────────

function renderSpendChart(breakdown) {
  const container = document.getElementById("spend-chart");
  const entries = Object.entries(breakdown).sort((a, b) => b[1].total_spend - a[1].total_spend);
  if (!entries.length) {
    container.innerHTML = '<span class="chart-empty">Launch jobs to see spend breakdown.</span>';
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v.total_spend), 0.0001);
  container.innerHTML = entries.map(([pid, stats]) => {
    const pct = (stats.total_spend / max) * 100;
    const label = pid.split("-").slice(0, 2).join("-");
    return `
      <div class="chart-row">
        <div class="chart-label" title="${pid}">${label}</div>
        <div class="chart-bar-wrap">
          <div class="chart-bar" style="width:${pct}%"></div>
        </div>
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
    const card = document.getElementById("audit-card");
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
        <div class="audit-detail">
          <span class="audit-user">${e.user}</span> → ${e.provider_id}
        </div>
      </div>`).join("");
  } catch { document.getElementById("audit-card").style.display = "none"; }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let _toastTimer = null;
function showToast(msg, type = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { t.className = ""; }, 3500);
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
    loadProviders();
    refreshHistory();
    refreshAnalytics();
    refreshAuditLog();
  });

  document.getElementById("auto-pick-btn").addEventListener("click", () => launchJob(null));
  document.getElementById("export-csv-btn").addEventListener("click", exportCSV);

  loadProviders();
  refreshAnalytics();
  refreshRateLimit();

  // Refresh providers + analytics every 15s, rate limit every 5s
  setInterval(() => { loadProviders(); refreshAnalytics(); refreshHistory(); }, 15000);
  setInterval(refreshRateLimit, 5000);
});
