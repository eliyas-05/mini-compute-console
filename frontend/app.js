const API_BASE = "http://localhost:8000";
const JOB_DURATION_SECONDS = 90;

let currentJobId = null;
let pollInterval = null;
let apiKey = "demo-key-123";

// ── Brand ────────────────────────────────────────────────────────────────────

async function loadBrand(brandName) {
  try {
    const res = await fetch(`${API_BASE}/brand/${brandName}`);
    if (!res.ok) return;
    const brand = await res.json();

    document.documentElement.style.setProperty("--primary", brand.primary_color);
    document.documentElement.style.setProperty("--accent", brand.accent_color);
    document.documentElement.style.setProperty("--bg", brand.bg_color);
    document.documentElement.style.setProperty("--card", brand.card_color);
    document.documentElement.style.setProperty("--text", brand.text_color);
    document.documentElement.style.setProperty("--muted", brand.muted_color);

    document.getElementById("logo-text").textContent = brand.logo_text;
    document.getElementById("tagline-text").textContent = brand.tagline;
    document.title = brand.display_name;

    document.querySelectorAll(".brand-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.brand === brandName);
    });

    // Update URL without reload
    const url = new URL(window.location);
    url.searchParams.set("brand", brandName);
    window.history.replaceState({}, "", url);
  } catch (e) {
    console.error("Brand load failed:", e);
  }
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const key = document.getElementById("api-key-input").value.trim() || apiKey;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "X-API-Key": key,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── Providers ─────────────────────────────────────────────────────────────────

async function loadProviders() {
  try {
    const providers = await apiFetch("/providers");
    renderProviders(providers);
  } catch (e) {
    showToast(`Failed to load providers: ${e.message}`, "error");
  }
}

function renderProviders(providers) {
  const tbody = document.getElementById("provider-tbody");
  tbody.innerHTML = "";

  providers.forEach(p => {
    const uptimeClass = p.uptime_pct >= 99 ? "uptime-high" : p.uptime_pct >= 98 ? "uptime-med" : "uptime-low";
    const dotClass = p.status === "available" ? "dot-available" : "dot-busy";
    const available = p.status === "available";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <div class="provider-name">${p.name}</div>
        <div class="provider-region">${p.region}</div>
      </td>
      <td><span class="gpu-badge">${p.gpu_type}</span></td>
      <td class="price">$${p.price_per_hour.toFixed(2)}<span class="price-unit">/hr</span></td>
      <td class="uptime ${uptimeClass}">${p.uptime_pct}%</td>
      <td><span class="status-dot ${dotClass}"></span>${p.status}</td>
      <td>
        <button class="btn btn-primary btn-sm" ${available ? "" : "disabled"}
          onclick="launchJob('${p.id}')">
          Launch
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ── Launch ────────────────────────────────────────────────────────────────────

async function launchJob(providerId) {
  const body = providerId ? { provider_id: providerId } : {};
  try {
    const job = await apiFetch("/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    });
    currentJobId = job.job_id;
    showToast(`Job ${job.job_id} launched on ${job.provider_name} (${job.gpu_type})`, "success");
    startPolling();
    renderJobCard(job);
    refreshAuditLog();
  } catch (e) {
    showToast(`Launch failed: ${e.message}`, "error");
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollJob, 2000);
}

async function pollJob() {
  if (!currentJobId) return;
  try {
    const [job, logsData] = await Promise.all([
      apiFetch(`/jobs/${currentJobId}`),
      apiFetch(`/jobs/${currentJobId}/logs`),
    ]);
    renderJobCard(job, logsData.logs);
    if (job.status === "complete") {
      clearInterval(pollInterval);
      refreshAuditLog();
    }
  } catch (e) {
    console.error("Poll error:", e);
  }
}

// ── Render job card ───────────────────────────────────────────────────────────

function renderJobCard(job, logs = []) {
  const panel = document.getElementById("job-panel");
  const elapsed = estimateElapsed(job);
  const progress = Math.min((elapsed / JOB_DURATION_SECONDS) * 100, 100);

  const badgeClass = {
    queued: "badge-queued",
    running: "badge-running",
    complete: "badge-complete",
  }[job.status] || "badge-queued";

  panel.innerHTML = `
    <div class="job-header">
      <div>
        <div class="job-id">JOB-${job.job_id.toUpperCase()}</div>
        <div class="job-provider">${job.provider_name} · ${job.gpu_type}</div>
        <div class="job-detail">${job.region} · $${job.price_per_hour.toFixed(2)}/hr</div>
      </div>
      <span class="job-status-badge ${badgeClass}">${job.status}</span>
    </div>

    <div class="cost-display">
      <div>
        <div class="cost-label">Running Cost</div>
        <div class="cost-value">$${job.cost_so_far.toFixed(4)}</div>
      </div>
      <div class="cost-rate">$${job.price_per_hour.toFixed(2)}/hr</div>
    </div>

    <div class="progress-bar-wrap">
      <div class="progress-bar-fill" style="width: ${progress}%"></div>
    </div>

    <div class="section-title" style="margin-top:16px">Live Logs</div>
    <div class="log-box" id="log-box">
      ${logs.length === 0
        ? '<span class="log-empty">Waiting for logs...</span>'
        : logs.map(l => `<div class="log-line">${escapeHtml(l)}</div>`).join("")
      }
    </div>
  `;

  // Auto-scroll logs
  const logBox = document.getElementById("log-box");
  if (logBox) logBox.scrollTop = logBox.scrollHeight;
}

function estimateElapsed(job) {
  // cost_so_far = elapsed_hours * price_per_hour
  if (job.price_per_hour === 0) return 0;
  return (job.cost_so_far / job.price_per_hour) * 3600;
}

// ── Audit log ─────────────────────────────────────────────────────────────────

async function refreshAuditLog() {
  const adminKey = document.getElementById("api-key-input").value.trim();
  if (adminKey !== "admin-key-456") return; // only show for admin key

  try {
    const entries = await apiFetch("/admin/audit");
    renderAuditLog(entries);
    document.getElementById("audit-card").style.display = "";
  } catch {
    document.getElementById("audit-card").style.display = "none";
  }
}

function renderAuditLog(entries) {
  const list = document.getElementById("audit-list");
  if (!entries.length) {
    list.innerHTML = '<span class="audit-empty">No activity yet.</span>';
    return;
  }
  list.innerHTML = entries.slice(0, 8).map(e => `
    <div class="audit-item">
      <div class="audit-item-top">
        <span class="audit-job-id">${e.job_id}</span>
        <span class="audit-ts">${new Date(e.timestamp).toLocaleTimeString()}</span>
      </div>
      <div class="audit-detail">
        <span class="audit-user">${e.user}</span> → ${e.provider_id}
      </div>
    </div>
  `).join("");
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let toastTimer = null;
function showToast(msg, type = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ""; }, 3500);
}

// ── Util ──────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  // Brand from query param
  const params = new URLSearchParams(window.location.search);
  const brand = params.get("brand") || "voltgrid";
  loadBrand(brand);

  // Brand toggle buttons
  document.querySelectorAll(".brand-btn").forEach(btn => {
    btn.addEventListener("click", () => loadBrand(btn.dataset.brand));
  });

  // API key input
  const keyInput = document.getElementById("api-key-input");
  keyInput.value = apiKey;
  keyInput.addEventListener("change", () => {
    loadProviders();
    refreshAuditLog();
  });

  // Auto-pick button
  document.getElementById("auto-pick-btn").addEventListener("click", () => launchJob(null));

  loadProviders();
  document.getElementById("audit-card").style.display = "none";

  // Reload providers every 30s
  setInterval(loadProviders, 30000);
});
