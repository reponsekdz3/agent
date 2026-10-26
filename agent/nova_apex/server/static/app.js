// NOVA-APEX Mission Control Client Engine
let socket = null;
let isPaused = false;

// Presets dictionary
const PRESETS = {
  create_account: "Navigate to GitHub signup portal, analyze the registration form, generate credentials, fill out the account fields, and store login to vault.",
  scaffold_fullstack: "Scaffold a complete modern project in workspace with frontend, backend, dockerfile, documentation, and configuration files.",
  desktop_audit: "Inspect desktop screen, list all active workspace directories, verify system integrity, and capture a verification snapshot.",
  web_research: "Browse the web, research current breakthrough developments in autonomous multimodal AI agents, and generate a summary report.",
  mobile_inspect: "Connect to Android device via ADB, capture current mobile screen frame, and dump UI element hierarchy."
};

function initApp() {
  connectWebSocket();
  pollStatus();
  pollTelemetry();
  loadVault();
  setInterval(pollStatus, 2000);
  setInterval(pollTelemetry, 10000);
}

function applyPreset(key) {
  if (PRESETS[key]) {
    document.getElementById("goal-prompt").value = PRESETS[key];
  }
}

// WebSocket Live Stream
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

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
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };

  socket.onclose = () => {
    appendLog({ level: "WARNING", domain: "NETWORK", message: "Telemetry link lost. Reconnecting in 3s..." });
    setTimeout(connectWebSocket, 3000);
  };
}

function appendLog(log) {
  const term = document.getElementById("terminal-body");
  const row = document.createElement("div");
  const lvl = (log.level || "info").toLowerCase();
  row.className = `log-entry ${lvl}`;

  const timeStr = new Date(log.timestamp || Date.now()).toLocaleTimeString();
  row.innerText = `[${timeStr}] [${log.domain || 'AGENT'}] ${log.message}`;
  term.appendChild(row);

  // Auto-scroll
  term.scrollTop = term.scrollHeight;
}

function clearLogs() {
  document.getElementById("terminal-body").innerHTML = "";
}

// Actions
async function submitGoal() {
  const prompt = document.getElementById("goal-prompt").value.trim();
  if (!prompt) {
    showToast("Please enter an objective first.");
    return;
  }

  showToast("Dispatching mission to NOVA-APEX engine...");
  try {
    const res = await fetch("/api/goal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt })
    });
    const data = await res.json();
    if (res.ok) {
      showToast("Mission dispatched successfully!");
      pollStatus();
    } else {
      showToast("Error: " + data.detail);
    }
  } catch (err) {
    showToast("Failed to connect to agent server: " + err);
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
    showToast("Error updating pause state");
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

// Polling & Render
async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    renderStatus(data);
  } catch (e) {
    // offline or server restarting
  }
}

function renderStatus(data) {
  const statusPill = document.getElementById("agent-status-pill");
  const statusText = document.getElementById("agent-status-text");

  if (!data || data.status === "idle") {
    statusText.innerText = "SYSTEM IDLE";
    statusPill.style.borderColor = "rgba(255,255,255,0.2)";
    return;
  }

  const rawStatus = (data.status || "idle").toUpperCase();
  statusText.innerText = `STATUS: ${rawStatus}`;

  if (rawStatus === "EXECUTING") {
    statusPill.style.borderColor = "var(--accent-cyan)";
  } else if (rawStatus === "SUCCESS") {
    statusPill.style.borderColor = "var(--accent-green)";
  } else if (rawStatus === "FAILED") {
    statusPill.style.borderColor = "var(--accent-red)";
  }

  // Render Steps Graph
  const stepsList = document.getElementById("steps-list");
  const counter = document.getElementById("step-counter");

  if (!data.steps || data.steps.length === 0) {
    stepsList.innerHTML = `<div class="empty-state">No steps in plan yet.</div>`;
    counter.innerText = "0 / 0 Steps";
    return;
  }

  const completedCount = data.steps.filter(s => s.status === "success").length;
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

    // If step has screenshot, update viewport
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
  badge.innerText = (domain || "LIVE").toUpperCase();
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

    // Normalize coordinates based on natural image size
    const normX = Math.round((clickX / rect.width) * (screenImg.naturalWidth || 1280));
    const normY = Math.round((clickY / rect.height) * (screenImg.naturalHeight || 800));

    const badge = document.getElementById("viewport-domain-badge");
    const domain = (badge.innerText || "desktop").toLowerCase();

    showToast(`Direct Click dispatched: (${normX}, ${normY}) on [${domain}]`);

    try {
      const res = await fetch("/api/interact/click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x: normX, y: normY, domain: domain.includes("browser") ? "browser" : "desktop" })
      });
      const data = await res.json();
      if (data.screenshot) {
        updateViewport(data.screenshot, domain);
      }
    } catch (err) {
      console.error("Direct click failed", err);
    }
  });
}

window.addEventListener("DOMContentLoaded", () => {
  initApp();
  setupInteractiveViewport();
});
