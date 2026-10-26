// NOVA-APEX Mission Control Dynamic Client Engine
let socket = null;
let isPaused = false;
let isHeaded = false;

// Presets dictionary
const PRESETS = {
  navigate_github: "Launch browser and navigate to https://github.com, inspect the page DOM, and capture high-res verification screenshot.",
  create_account: "Navigate to GitHub signup portal at https://github.com/signup, inspect registration fields, generate secure credentials, fill out the account form, and store credentials to vault.",
  scaffold_fullstack: "Scaffold a complete modern project in workspace with frontend, backend, dockerfile, documentation, and configuration files.",
  desktop_audit: "Inspect desktop screen, list all active workspace directories, verify system integrity, and capture a verification snapshot.",
  web_research: "Browse the web, research current breakthrough developments in autonomous multimodal AI agents, and generate a summary report.",
  hardware_inspect: "Enumerate hardware displays, storage drives, and list all visible Windows applications."
};

function initApp() {
  connectWebSocket();
  pollStatus();
  pollTelemetry();
  loadVault();
  setInterval(pollStatus, 1500);
  setInterval(pollTelemetry, 10000);
}

function applyPreset(key) {
  if (PRESETS[key]) {
    document.getElementById("goal-prompt").value = PRESETS[key];
    // If it's a web preset, also put the URL in the browser URL bar
    if (key === "navigate_github" || key === "create_account") {
      document.getElementById("browser-url-bar").value = key === "create_account" ? "github.com/signup" : "github.com";
    }
  }
}

// WebSocket Live Telemetry Stream
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  try {
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      appendLog({ level: "SYSTEM", domain: "NETWORK", message: "Real-time telemetry link established." });
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        appendLog(data);

        // Check for screenshot updates in log data
        if (data.data && data.data.screenshot_path) {
          updateViewport(data.data.screenshot_path, data.domain);
        }
      } catch (e) {}
    };

    socket.onclose = () => {
      setTimeout(connectWebSocket, 4000);
    };

    socket.onerror = () => {
      socket.close();
    };
  } catch (err) {
    setTimeout(connectWebSocket, 4000);
  }
}

function appendLog(log) {
  const term = document.getElementById("terminal-body");
  if (!term) return;

  const row = document.createElement("div");
  const lvl = (log.level || "info").toLowerCase();
  row.className = `log-entry ${lvl}`;

  const timeStr = new Date(log.timestamp || Date.now()).toLocaleTimeString();
  row.innerText = `[${timeStr}] [${log.domain || 'AGENT'}] ${log.message}`;
  term.appendChild(row);

  term.scrollTop = term.scrollHeight;
}

function clearLogs() {
  document.getElementById("terminal-body").innerHTML = "";
}

// --- Mission Control Actions ---
async function submitGoal() {
  const promptInput = document.getElementById("goal-prompt");
  const prompt = promptInput.value.trim();
  const runBtn = document.getElementById("btn-run");
  const runBtnText = document.getElementById("run-btn-text");
  const progressContainer = document.getElementById("progress-container");
  const progressFill = document.getElementById("progress-fill");
  const progressLabel = document.getElementById("progress-label");
  const stepsList = document.getElementById("steps-list");

  if (!prompt) {
    showToast("Please enter an objective or select a preset first.");
    return;
  }

  // Immediate UI Feedback
  runBtn.disabled = true;
  runBtnText.innerText = "PLANNING...";
  progressContainer.style.display = "block";
  progressFill.style.width = "15%";
  progressLabel.innerText = "Synthesizing execution graph...";

  stepsList.innerHTML = `
    <div class="step-card in_progress">
      <div class="step-info">
        <div class="step-title-line">
          <span class="step-number">⚡</span>
          <span class="step-title">Formulating Multi-Domain Autonomous Plan...</span>
        </div>
        <span class="step-desc">Deconstructing objective into sequential milestones...</span>
      </div>
      <div class="step-badge in_progress">PLANNING</div>
    </div>
  `;

  showToast("Dispatching mission to NOVA-APEX engine...");

  try {
    const res = await fetch("/api/goal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt })
    });
    const data = await res.json();
    if (res.ok) {
      showToast("Mission registered & executing!");
      setTimeout(pollStatus, 500);
    } else {
      showToast("Error: " + (data.detail || "Failed to schedule"));
      runBtn.disabled = false;
      runBtnText.innerText = "EXECUTE MISSION";
    }
  } catch (err) {
    showToast("Failed to reach server: " + err);
    runBtn.disabled = false;
    runBtnText.innerText = "EXECUTE MISSION";
  }
}

async function togglePause() {
  const endpoint = isPaused ? "/api/resume" : "/api/pause";
  try {
    const res = await fetch(endpoint, { method: "POST" });
    if (res.ok) {
      isPaused = !isPaused;
      document.getElementById("btn-pause").innerHTML = isPaused ? 
        `<span class="btn-icon">▶</span> RESUME` : 
        `<span class="btn-icon">⏸</span> PAUSE`;
      showToast(isPaused ? "Execution paused" : "Execution resumed");
    }
  } catch (e) {
    showToast("Error toggling pause state");
  }
}

async function abortGoal() {
  if (confirm("Are you sure you want to abort the active mission?")) {
    try {
      await fetch("/api/abort", { method: "POST" });
      showToast("Mission aborted.");
      pollStatus();
    } catch (e) {
      showToast("Error aborting mission");
    }
  }
}

// --- Direct Interactive Browser Navigation ---
async function directNavigate() {
  let url = document.getElementById("browser-url-bar").value.trim();
  if (!url) {
    showToast("Please enter a URL to navigate.");
    return;
  }
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = "https://" + url;
  }

  showToast(`Navigating to ${url}...`);
  updateDomainBadge("BROWSER: NAVIGATING");

  try {
    const res = await fetch("/api/browser/navigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Arrived at: ${data.data ? data.data.title : url}`);
      if (data.screenshot) {
        updateViewport(data.screenshot, "BROWSER");
      }
    } else {
      showToast(`Navigation error: ${data.error}`);
    }
  } catch (e) {
    showToast("Navigation failed: " + e);
  }
}

async function directBrowserAction(action, target = null) {
  showToast(`Dispatching browser action: ${action}...`);
  try {
    const res = await fetch("/api/browser/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, target })
    });
    const data = await res.json();
    if (data.screenshot) {
      updateViewport(data.screenshot, "BROWSER");
    }
    showToast(data.success ? `Action ${action} completed.` : `Action failed: ${data.error}`);
  } catch (e) {
    showToast("Action error: " + e);
  }
}

async function toggleBrowserVisibility() {
  try {
    const res = await fetch("/api/browser/toggle-mode", { method: "POST" });
    const data = await res.json();
    const btn = document.getElementById("btn-browser-mode");
    if (data.headless) {
      btn.innerText = "🖥️ Mode: Headless";
      btn.style.color = "var(--accent-cyan)";
    } else {
      btn.innerText = "🖥️ Mode: Visible Chrome";
      btn.style.color = "var(--accent-green)";
    }
    showToast(`Browser mode switched to: ${data.mode}`);
  } catch (e) {
    showToast("Error toggling mode");
  }
}

// --- Polling & Render Engine ---
async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    renderStatus(data);
  } catch (e) {}
}

function renderStatus(data) {
  const statusPill = document.getElementById("agent-status-pill");
  const statusText = document.getElementById("agent-status-text");
  const runBtn = document.getElementById("btn-run");
  const runBtnText = document.getElementById("run-btn-text");
  const progressContainer = document.getElementById("progress-container");
  const progressFill = document.getElementById("progress-fill");
  const progressLabel = document.getElementById("progress-label");
  const stepsList = document.getElementById("steps-list");
  const counter = document.getElementById("step-counter");

  if (!data || data.status === "idle") {
    statusText.innerText = "SYSTEM READY";
    statusPill.style.borderColor = "rgba(255,255,255,0.2)";
    runBtn.disabled = false;
    runBtnText.innerText = "EXECUTE MISSION";
    progressContainer.style.display = "none";
    return;
  }

  const rawStatus = (data.status || "idle").toUpperCase();
  statusText.innerText = `STATUS: ${rawStatus}`;

  if (rawStatus === "PLANNING") {
    statusPill.style.borderColor = "var(--accent-cyan)";
    runBtn.disabled = true;
    runBtnText.innerText = "PLANNING...";
    progressContainer.style.display = "block";
    progressFill.style.width = "25%";
    progressLabel.innerText = "Formulating milestones...";
    return;
  } else if (rawStatus === "EXECUTING") {
    statusPill.style.borderColor = "var(--accent-cyan)";
    runBtn.disabled = true;
    runBtnText.innerText = "EXECUTING...";
    progressContainer.style.display = "block";
  } else if (rawStatus === "SUCCESS") {
    statusPill.style.borderColor = "var(--accent-green)";
    runBtn.disabled = false;
    runBtnText.innerText = "EXECUTE MISSION";
    progressFill.style.width = "100%";
    progressLabel.innerText = "100% COMPLETE";
  } else if (rawStatus === "FAILED") {
    statusPill.style.borderColor = "var(--accent-red)";
    runBtn.disabled = false;
    runBtnText.innerText = "EXECUTE MISSION";
    progressLabel.innerText = "FAILED";
  }

  // Render Steps Graph
  if (!data.steps || data.steps.length === 0) {
    return;
  }

  const completedCount = data.steps.filter(s => s.status === "success").length;
  const pct = Math.round((completedCount / data.steps.length) * 100);

  if (rawStatus === "EXECUTING") {
    progressFill.style.width = `${Math.max(pct, 20)}%`;
    progressLabel.innerText = `${completedCount}/${data.steps.length} Milestones (${pct}%)`;
  }

  counter.innerText = `${completedCount} / ${data.steps.length} Milestones`;

  stepsList.innerHTML = "";
  data.steps.forEach(step => {
    const card = document.createElement("div");
    card.className = `step-card ${step.status}`;

    card.innerHTML = `
      <div class="step-info">
        <div class="step-title-line">
          <span class="step-number">#${step.step_id}</span>
          <span class="step-title">${step.title}</span>
        </div>
        <span class="step-desc">${step.description}</span>
      </div>
      <div class="step-badge ${step.status}">${step.status}</div>
    `;
    stepsList.appendChild(card);

    if (step.result && step.result.screenshot_path) {
      updateViewport(step.result.screenshot_path, step.domain);
    }
  });
}

function updateViewport(screenshotPath, domain) {
  if (!screenshotPath) return;
  const filename = screenshotPath.split(/[\/\\]/).pop();
  const screenImg = document.getElementById("screen-img");
  const placeholder = document.getElementById("screen-placeholder");
  const badge = document.getElementById("viewport-domain-badge");

  screenImg.src = `/api/artifacts/${filename}?t=${Date.now()}`;
  screenImg.style.display = "block";
  placeholder.style.display = "none";
  if (badge) {
    badge.innerText = (domain || "LIVE").toUpperCase();
  }
}

function updateDomainBadge(text) {
  const badge = document.getElementById("viewport-domain-badge");
  if (badge) badge.innerText = text;
}

async function pollTelemetry() {
  try {
    const res = await fetch("/api/telemetry");
    const data = await res.json();
    document.getElementById("disk-info").innerText = `Free: ${data.free_disk_gb} GB`;
  } catch (e) {}
}

async function loadVault() {
  try {
    const res = await fetch("/api/vault");
    const data = await res.json();
    const vaultList = document.getElementById("vault-list");

    if (!data.created_accounts || data.created_accounts.length === 0) {
      vaultList.innerHTML = `<div class="vault-empty">No credentials generated yet.</div>`;
      return;
    }

    vaultList.innerHTML = "";
    data.created_accounts.forEach(acc => {
      const entry = document.createElement("div");
      entry.className = "vault-entry";
      entry.innerHTML = `
        <span class="vault-service">${acc.service}</span>
        <span class="vault-user">👤 ${acc.username}</span>
      `;
      vaultList.appendChild(entry);
    });
  } catch (e) {}
}

function setupInteractiveViewport() {
  const screenImg = document.getElementById("screen-img");
  if (!screenImg) return;

  screenImg.addEventListener("click", async (e) => {
    const rect = screenImg.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const normX = Math.round((clickX / rect.width) * (screenImg.naturalWidth || 1280));
    const normY = Math.round((clickY / rect.height) * (screenImg.naturalHeight || 800));

    const badge = document.getElementById("viewport-domain-badge");
    const domainText = (badge ? badge.innerText : "desktop").toLowerCase();

    showToast(`Dispatching Direct Click at (${normX}, ${normY}) on ${domainText}`);

    try {
      const res = await fetch("/api/interact/click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x: normX, y: normY, domain: domainText.includes("browser") ? "browser" : "desktop" })
      });
      const data = await res.json();
      if (data.screenshot) {
        updateViewport(data.screenshot, domainText);
      }
    } catch (err) {
      console.error("Direct click failed", err);
    }
  });
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.innerText = msg;
  toast.classList.add("visible");
  setTimeout(() => toast.classList.remove("visible"), 3200);
}

window.addEventListener("DOMContentLoaded", () => {
  initApp();
  setupInteractiveViewport();
});
