// NOVA-APEX Mission Control Dynamic Client Engine
let socket = null;
let isPaused = false;
let isHeaded = false;
let authRequired = false;
let csrfToken = null;
let dashboardStarted = false;
let controllerReachable = false;
let statusPollTimer = null;
let telemetryPollTimer = null;
let browserTabsPollTimer = null;
let websocketReconnectTimer = null;
const nativeFetch = window.fetch.bind(window);

window.fetch = async (input, init = {}) => {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (authRequired && csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await nativeFetch(input, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && !["/api/auth/status", "/api/auth/login"].includes(new URL(input, window.location.href).pathname)) {
    authRequired = true;
    showAuthOverlay();
  }
  return response;
};

// Presets dictionary
const PRESETS = {
  navigate_github: "Launch browser and navigate to https://github.com, inspect the page DOM, and capture high-res verification screenshot.",
  create_account: "Navigate to GitHub signup portal at https://github.com/signup, inspect registration fields, fill the form for review, and stop before final submission.",
  assisted_order_booking: "Search and compare options for the product or service I describe. Summarize availability, prices, and important terms, prepare a draft selection for my review, then stop before checkout, purchase, reservation, booking, payment, or final submission.",
  scaffold_fullstack: "Scaffold a complete modern project in workspace with frontend, backend, dockerfile, documentation, and configuration files.",
  desktop_audit: "Inspect desktop screen, list all active workspace directories, verify system integrity, and capture a verification snapshot.",
  web_research: "Browse the web, research current breakthrough developments in autonomous multimodal AI agents, and generate a summary report.",
  hardware_inspect: "Enumerate hardware displays, storage drives, and list all visible Windows applications."
};

async function initApp() {
  const loginForm = document.getElementById("login-form");
  loginForm.addEventListener("submit", login);
  window.addEventListener("online", updateNetworkStatus);
  window.addEventListener("offline", updateNetworkStatus);

  try {
    if ("serviceWorker" in navigator) {
      try {
        await navigator.serviceWorker.register("/service-worker.js");
      } catch (error) {
        appendLog({ level: "WARNING", domain: "OFFLINE", message: `Offline app shell is unavailable: ${error.message}` });
      }
    }
    const response = await fetch("/api/auth/status");
    if (!response.ok) throw new Error(`Authentication status failed (${response.status})`);
    const status = await response.json();
    authRequired = status.required;
    csrfToken = status.csrf_token;
    updateNetworkStatus();
    if (status.required && !status.authenticated) {
      showAuthOverlay();
      return;
    }
    startDashboard();
  } catch (error) {
    showToast(`Controller unavailable; local queue is available. ${error.message}`);
    updateNetworkStatus(false);
    startDashboard();
  }
}

async function decideApproval(approved) {
  try {
    const response = await fetch(approved ? "/api/approval/approve" : "/api/approval/reject", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not record the action decision.");
    showToast(approved ? "Action approved; it may now run." : "Action rejected.");
    pollStatus();
  } catch (error) {
    showToast(`Approval update failed: ${error.message}`);
  }
}

function startDashboard() {
  document.getElementById("auth-overlay").hidden = true;
  document.getElementById("btn-logout").hidden = !authRequired;
  if (dashboardStarted) {
    if (!socket || socket.readyState === WebSocket.CLOSED) connectWebSocket();
    pollStatus();
    return;
  }
  dashboardStarted = true;
  connectWebSocket();
  pollStatus();
  pollTelemetry();
  loadBrowserTabs();
  loadVault();
  loadOfflineQueue();
  statusPollTimer = setInterval(pollStatus, 1500);
  telemetryPollTimer = setInterval(pollTelemetry, 10000);
  browserTabsPollTimer = setInterval(loadBrowserTabs, 5000);
}

async function logout() {
  try {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (!response.ok) throw new Error(`Sign out failed (${response.status})`);
    csrfToken = null;
    dashboardStarted = false;
    clearInterval(statusPollTimer);
    clearInterval(telemetryPollTimer);
    clearInterval(browserTabsPollTimer);
    clearTimeout(websocketReconnectTimer);
    statusPollTimer = telemetryPollTimer = browserTabsPollTimer = websocketReconnectTimer = null;
    if (socket) {
      socket.onclose = null;
      socket.close();
      socket = null;
    }
    showAuthOverlay();
  } catch (error) {
    showToast(`Unable to sign out: ${error.message}`);
  }
}

function showAuthOverlay() {
  document.getElementById("auth-overlay").hidden = false;
  document.getElementById("auth-password").focus();
}

async function login(event) {
  event.preventDefault();
  const error = document.getElementById("auth-error");
  const password = document.getElementById("auth-password").value;
  error.hidden = true;
  try {
    const response = await nativeFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ password })
    });
    const data = await response.json();
    if (!response.ok) {
      error.textContent = data.detail || "Sign-in failed.";
      error.hidden = false;
      return;
    }
    authRequired = true;
    csrfToken = data.csrf_token;
    document.getElementById("auth-password").value = "";
    startDashboard();
  } catch (exception) {
    error.textContent = `Unable to sign in: ${exception.message}`;
    error.hidden = false;
  }
}

function updateNetworkStatus(controllerStatus) {
  const network = document.getElementById("network-status");
  const controller = document.getElementById("controller-status");
  if (network) {
    network.innerText = navigator.onLine ? "NETWORK: ONLINE" : "NETWORK: OFFLINE";
    network.classList.toggle("offline", !navigator.onLine);
  }
  if (typeof controllerStatus === "boolean") controllerReachable = controllerStatus;
  if (controller) {
    controller.innerText = controllerReachable ? "CONTROLLER: READY" : "CONTROLLER: UNAVAILABLE";
    controller.classList.toggle("offline", !controllerReachable);
  }
  const runButton = document.getElementById("btn-run");
  if (runButton) runButton.disabled = !controllerReachable;
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
      clearTimeout(websocketReconnectTimer);
      websocketReconnectTimer = null;
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
      socket = null;
      if (dashboardStarted && !websocketReconnectTimer) {
        websocketReconnectTimer = setTimeout(() => {
          websocketReconnectTimer = null;
          connectWebSocket();
        }, 4000);
      }
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

function openQueueDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("nova-apex-mission-queue", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("missions", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open the local mission queue."));
  });
}

async function getQueuedMissions() {
  const db = await openQueueDatabase();
  return new Promise((resolve, reject) => {
    const request = db.transaction("missions", "readonly").objectStore("missions").getAll();
    request.onsuccess = () => resolve(request.result.sort((a, b) => a.createdAt - b.createdAt));
    request.onerror = () => reject(request.error || new Error("Could not read the local mission queue."));
  });
}

async function queueMission() {
  const prompt = document.getElementById("goal-prompt").value.trim();
  if (!prompt) {
    showToast("Enter a mission before queuing it for review.");
    return;
  }
  try {
    const db = await openQueueDatabase();
    const id = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await new Promise((resolve, reject) => {
      const transaction = db.transaction("missions", "readwrite");
      transaction.objectStore("missions").add({ id, prompt, createdAt: Date.now() });
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error || new Error("Could not save the mission."));
    });
    await loadOfflineQueue();
    showToast("Mission saved on this device. It will not run until you review and send it.");
  } catch (error) {
    showToast(`Unable to queue mission: ${error.message}`);
  }
}

async function loadOfflineQueue() {
  const container = document.getElementById("offline-queue-list");
  if (!container || !("indexedDB" in window)) return;
  try {
    const missions = await getQueuedMissions();
    document.getElementById("queue-count").innerText = `${missions.length} pending`;
    container.replaceChildren();
    if (!missions.length) {
      container.innerHTML = `<div class="empty-state">No queued missions.</div>`;
      return;
    }
    missions.forEach((mission) => {
      const card = document.createElement("div");
      card.className = "queued-mission";
      const prompt = document.createElement("p");
      prompt.textContent = mission.prompt;
      const actions = document.createElement("div");
      actions.className = "queued-mission-actions";
      const send = document.createElement("button");
      send.className = "btn-sm";
      send.textContent = "Review & send";
      send.addEventListener("click", () => sendQueuedMission(mission));
      const remove = document.createElement("button");
      remove.className = "btn-danger-sm";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => removeQueuedMission(mission.id));
      actions.append(send, remove);
      card.append(prompt, actions);
      container.appendChild(card);
    });
  } catch (error) {
    container.innerHTML = `<div class="empty-state">Queue unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

async function sendQueuedMission(mission) {
  if (!confirm(`Review this mission before sending it to the controller:\n\n${mission.prompt}\n\nIt may perform actions on your devices or external websites.`)) return;
  if (!controllerReachable) {
    showToast("The controller is unavailable. This mission remains queued.");
    return;
  }
  try {
    const response = await fetch("/api/goal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: mission.prompt })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    await removeQueuedMission(mission.id, false);
    showToast("Mission sent. Review the live execution status.");
    pollStatus();
  } catch (error) {
    showToast(`Mission was not sent: ${error.message}`);
  }
}

async function removeQueuedMission(id, refresh = true) {
  const db = await openQueueDatabase();
  await new Promise((resolve, reject) => {
    const transaction = db.transaction("missions", "readwrite");
    transaction.objectStore("missions").delete(id);
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error || new Error("Could not remove queued mission."));
  });
  if (refresh) await loadOfflineQueue();
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
  let confirmed = false;
  if (action === "click_element" || action === "submit_form") {
    confirmed = confirm("Perform this action on the current website? It may submit a form, place an order, make a purchase, or book a reservation.");
    if (!confirmed) return;
  }
  if (action === "evaluate_js") {
    confirmed = confirm("Run the supplied JavaScript in the current website page?");
    if (!confirmed) return;
  }
  showToast(`Dispatching browser action: ${action}...`);
  try {
    const res = await fetch("/api/browser/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        target,
        confirmed,
        email: action === "create_account"
          ? document.getElementById("registration-email").value.trim() || null
          : null
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Browser request failed (${res.status})`);
    if (data.screenshot) {
      updateViewport(data.screenshot, "BROWSER");
    }
    showToast(data.success ? `Action ${action} completed.` : `Action failed: ${data.error}`);
    await loadBrowserTabs();
  } catch (e) {
    showToast("Action error: " + e.message);
  }
}

async function loadBrowserTabs() {
  const container = document.getElementById("browser-tabs-list");
  if (!container || !dashboardStarted) return;
  try {
    const response = await fetch("/api/manage/browser/tabs");
    if (!response.ok) throw new Error(`Tab request failed (${response.status})`);
    const data = await response.json();
    container.replaceChildren();
    if (!data.tabs || data.tabs.length === 0) {
      const empty = document.createElement("span");
      empty.className = "empty-state";
      empty.textContent = "No browser tabs are open.";
      container.appendChild(empty);
      return;
    }
    data.tabs.forEach((tab) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `browser-tab${tab.is_active ? " active" : ""}`;
      button.textContent = `${tab.title || "Untitled"} — ${tab.url}`;
      button.title = tab.url;
      button.addEventListener("click", () => directBrowserAction("switch_tab", String(tab.index)));
      container.appendChild(button);
    });
  } catch (error) {
    container.textContent = `Browser tabs unavailable: ${error.message}`;
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
    if (!res.ok) throw new Error(`Controller status failed (${res.status})`);
    const data = await res.json();
    updateNetworkStatus(true);
    renderStatus(data);
  } catch (e) {
    updateNetworkStatus(false);
  }
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
  const approvalPanel = document.getElementById("approval-panel");
  const approvalDescription = document.getElementById("approval-description");
  const pendingApproval = data && data.pending_approval;
  approvalPanel.hidden = !pendingApproval;
  if (pendingApproval) {
    approvalDescription.textContent =
      `${pendingApproval.title || "Action"}: ${pendingApproval.description || pendingApproval.action_type} ` +
      `${pendingApproval.target ? `Target: ${pendingApproval.target}. ` : ""}` +
      `(${pendingApproval.domain} / ${pendingApproval.action_type}). Approving may cause an external change.`;
  }

  if (!data || data.status === "idle") {
    statusText.innerText = "SYSTEM READY";
    statusPill.style.borderColor = "rgba(255,255,255,0.2)";
    runBtn.disabled = !controllerReachable;
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
  } else if (rawStatus === "WAITING_HUMAN") {
    statusPill.style.borderColor = "var(--accent-yellow)";
    runBtn.disabled = true;
    runBtnText.innerText = "WAITING FOR REVIEW";
    progressContainer.style.display = "block";
    progressLabel.innerText = "Review the pending action above.";
  } else if (rawStatus === "SUCCESS") {
    statusPill.style.borderColor = "var(--accent-green)";
    runBtn.disabled = !controllerReachable;
    runBtnText.innerText = "EXECUTE MISSION";
    progressFill.style.width = "100%";
    progressLabel.innerText = "100% COMPLETE";
  } else if (rawStatus === "FAILED") {
    statusPill.style.borderColor = "var(--accent-red)";
    runBtn.disabled = !controllerReachable;
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
          <span class="step-title">${escapeHtml(step.title)}</span>
        </div>
        <span class="step-desc">${escapeHtml(step.description)}</span>
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
  loadVaultTable();
}

// =========================================================================
// OMNI HUB TAB SWITCHING & MANAGEMENT ENGINES
// =========================================================================

let currentTab = "terminal";
let activeFilePath = null;

function switchHubTab(tabName) {
  currentTab = tabName;
  const tabs = ["terminal", "workspace", "os", "mobile", "vault"];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-btn-${t}`);
    const content = document.getElementById(`tab-${t}`);
    if (btn) {
      if (t === tabName) btn.classList.add("active");
      else btn.classList.remove("active");
    }
    if (content) {
      content.style.display = (t === tabName) ? "grid" : "none";
    }
  });

  if (tabName === "workspace") {
    loadWorkspaceTree();
  } else if (tabName === "os") {
    loadWindowsList();
    loadProcessList();
  } else if (tabName === "mobile") {
    loadMobileDetails();
  } else if (tabName === "vault") {
    loadVaultTable();
  }
}

// 1. Workspace File Explorer
async function loadWorkspaceTree() {
  const container = document.getElementById("file-tree-list");
  if (!container) return;
  container.innerHTML = `<div class="empty-state">Loading workspace tree...</div>`;

  try {
    const res = await fetch("/api/manage/workspace/tree");
    const data = await res.json();
    if (!data.items || data.items.length === 0) {
      container.innerHTML = `<div class="empty-state">Workspace is empty. Create a file above or execute a mission.</div>`;
      return;
    }

    container.innerHTML = "";
    data.items.forEach(item => {
      const node = document.createElement("div");
      node.className = `tree-node ${item.path === activeFilePath ? 'file-active' : ''}`;
      const icon = item.type === "directory" ? "📁" : "📄";
      const sizeStr = item.type === "file" ? `${item.size} B` : "";

      node.innerHTML = `
        <div class="node-info">
          <span>${icon}</span>
          <span>${escapeHtml(item.path)}</span>
        </div>
        <span class="node-size">${sizeStr}</span>
      `;

      if (item.type === "file") {
        node.onclick = () => openWorkspaceFile(item.path);
      }
      container.appendChild(node);
    });
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Failed to load tree: ${e}</div>`;
  }
}

async function openWorkspaceFile(path) {
  activeFilePath = path;
  document.getElementById("active-file-title").innerText = `FILE: ${path}`;
  const editor = document.getElementById("file-editor-content");
  editor.value = "Loading content...";

  document.querySelectorAll(".tree-node").forEach(node => {
    if (node.innerText.includes(path)) {
      node.classList.add("file-active");
    } else {
      node.classList.remove("file-active");
    }
  });

  try {
    const res = await fetch(`/api/manage/workspace/file?path=${encodeURIComponent(path)}`);
    if (res.ok) {
      const data = await res.json();
      editor.value = data.content;
      showToast(`Opened ${path}`);
    } else {
      showToast(`Failed to open ${path}`);
      editor.value = "";
    }
  } catch (e) {
    showToast(`Error reading file: ${e}`);
  }
}

async function saveActiveFile() {
  if (!activeFilePath) {
    const newName = prompt("Enter new file relative path (e.g. app.py, src/index.js):");
    if (!newName) return;
    activeFilePath = newName.trim();
  }

  const content = document.getElementById("file-editor-content").value;
  try {
    const res = await fetch("/api/manage/workspace/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: activeFilePath, content })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Saved ${activeFilePath} (${data.bytes} bytes)`);
      loadWorkspaceTree();
    } else {
      showToast("Error saving file");
    }
  } catch (e) {
    showToast("Error saving file: " + e);
  }
}

async function deleteActiveFile() {
  if (!activeFilePath) {
    showToast("No active file selected to delete.");
    return;
  }
  if (!confirm(`Are you sure you want to permanently delete '${activeFilePath}'?`)) return;

  try {
    const res = await fetch(`/api/manage/workspace/file?path=${encodeURIComponent(activeFilePath)}`, {
      method: "DELETE"
    });
    if (res.ok) {
      showToast(`Deleted ${activeFilePath}`);
      activeFilePath = null;
      document.getElementById("active-file-title").innerText = "FILE EDITOR";
      document.getElementById("file-editor-content").value = "";
      loadWorkspaceTree();
    } else {
      showToast("Failed to delete file");
    }
  } catch (e) {
    showToast("Error deleting file: " + e);
  }
}

// 2. OS Windows & Processes
async function loadWindowsList() {
  const tbody = document.getElementById("windows-table-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Scanning active windows...</td></tr>`;

  try {
    const res = await fetch("/api/manage/windows");
    const data = await res.json();
    if (!data.windows || data.windows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No visible windows found.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    data.windows.forEach(w => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge-tag cyan">HWND ${w.hwnd}</span></td>
        <td style="font-weight: 500;">${escapeHtml(w.title)}</td>
        <td>
          <button class="btn-sm" data-action="focus-window" data-hwnd="${Number(w.hwnd)}">🔍 Focus</button>
          <button class="btn-danger-sm" data-action="close-window" data-hwnd="${Number(w.hwnd)}">✕ Close</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Error scanning windows: ${e}</td></tr>`;
  }
}

async function focusWindow(hwnd) {
  try {
    const res = await fetch("/api/manage/windows/focus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hwnd })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Window HWND ${hwnd} focused`);
    } else {
      showToast(`Failed to focus HWND ${hwnd}`);
    }
  } catch (e) {
    showToast("Error focusing window: " + e);
  }
}

async function closeWindow(hwnd) {
  if (!confirm(`Send WM_CLOSE signal to HWND ${hwnd}?`)) return;
  try {
    const res = await fetch("/api/manage/windows/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hwnd })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Window HWND ${hwnd} closed.`);
      setTimeout(loadWindowsList, 1000);
    } else {
      showToast("Error closing window");
    }
  } catch (e) {
    showToast("Error: " + e);
  }
}

async function loadProcessList() {
  const tbody = document.getElementById("process-table-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Inspecting running processes...</td></tr>`;

  try {
    const res = await fetch("/api/manage/processes");
    const data = await res.json();
    if (!data.processes || data.processes.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No process data available.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    data.processes.forEach(p => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge-tag green">PID ${escapeHtml(p.Id || p.PID || '--')}</span></td>
        <td style="font-weight: 600;">${escapeHtml(p.ProcessName || p.Name || '--')}</td>
        <td>${escapeHtml(p.MemoryMB || '--')} MB</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Error loading processes: ${e}</td></tr>`;
  }
}

// 3. Mobile ADB Telemetry & OTP Interceptor
async function loadMobileDetails() {
  const card = document.getElementById("mobile-info-card");
  if (!card) return;
  card.innerHTML = `<div class="empty-state">Querying ADB hardware telemetry...</div>`;

  try {
    const res = await fetch("/api/manage/mobile/info");
    const data = await res.json();
    if (!data.connected) {
      card.innerHTML = `
        <div class="empty-state">
          ⚠️ No active Android device or emulator detected via ADB.<br>
          <span style="font-size: 11px; color: var(--text-muted); margin-top: 6px; display: inline-block;">
            Connect an Android device with USB debugging or start an Android virtual emulator.
          </span>
        </div>
      `;
      return;
    }

    card.innerHTML = `
      <label class="mobile-info-item" for="active-mobile-device">
        <span>Active device:</span>
        <select id="active-mobile-device" class="device-select"></select>
      </label>
      <div class="mobile-info-item">
        <span>Device ID:</span>
        <span class="badge-tag cyan">${escapeHtml(data.device_id || '--')}</span>
      </div>
      <div class="mobile-info-item">
        <span>Model:</span>
        <span style="font-weight: 600;">${escapeHtml(data.model || 'Generic Android')}</span>
      </div>
      <div class="mobile-info-item">
        <span>Android OS:</span>
        <span>Version ${escapeHtml(data.android_version || '--')}</span>
      </div>
      <div class="mobile-info-item">
        <span>Battery:</span>
        <span class="badge-tag green">${data.battery_level !== null ? data.battery_level + '%' : '--'}</span>
      </div>
    `;
    const selector = document.getElementById("active-mobile-device");
    data.devices.forEach((deviceId) => {
      const option = document.createElement("option");
      option.value = deviceId;
      option.textContent = deviceId;
      option.selected = deviceId === data.device_id;
      selector.appendChild(option);
    });
    selector.addEventListener("change", () => selectMobileDevice(selector.value));
  } catch (e) {
    card.innerHTML = `<div class="empty-state">ADB query error: ${e}</div>`;
  }
}

async function selectMobileDevice(deviceId) {
  try {
    const response = await fetch("/api/manage/mobile/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not select the Android device.");
    showToast(`Active Android device set to ${deviceId}`);
    await loadMobileDetails();
  } catch (error) {
    showToast(`Device selection failed: ${error.message}`);
  }
}

async function sendMobileKey(keycode) {
  showToast(`Dispatching ADB Keycode: ${keycode}...`);
  try {
    const res = await fetch("/api/manage/mobile/keyevent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keycode })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Keycode ${keycode} dispatched!`);
    } else {
      showToast(`ADB error: ${data.output || 'Failed'}`);
    }
  } catch (e) {
    showToast("Error sending mobile key: " + e);
  }
}

async function scanMobileOTP() {
  const box = document.getElementById("otp-interceptor-box");
  box.innerHTML = `<p>Scanning notification stream for 2FA / OTP codes...</p>`;
  try {
    const res = await fetch("/api/manage/mobile/otp");
    const data = await res.json();
    if (data.connected && data.otp) {
      box.replaceChildren();
      const heading = document.createElement("p");
      heading.style.color = "var(--accent-green)";
      heading.style.fontWeight = "700";
      heading.textContent = "OTP DETECTED";
      const otp = document.createElement("div");
      otp.className = "otp-code-display";
      otp.textContent = data.otp;
      const source = document.createElement("div");
      source.className = "otp-timestamp";
      source.textContent = `Source: Device ${data.device} • Just now`;
      const copy = document.createElement("button");
      copy.className = "btn-sm";
      copy.textContent = "Copy OTP Code";
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(String(data.otp));
          showToast("OTP copied to clipboard.");
        } catch (error) {
          showToast(`Unable to copy OTP: ${error.message}`);
        }
      });
      box.append(heading, otp, source, copy);
    } else {
      box.innerHTML = `
        <p>No new 2FA / verification codes found in notification stream.</p>
        <span class="sub-text">Send an SMS or trigger a 2FA prompt to the connected device and click Scan.</span>
      `;
      showToast(data.message || "No OTP codes found.");
    }
  } catch (e) {
    box.innerHTML = `<p>Error scanning for OTP: ${e}</p>`;
  }
}

// 4. Credential Vault Management
async function loadVaultTable() {
  const tbody = document.getElementById("vault-table-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Querying secure vault...</td></tr>`;

  try {
    const [vaultResponse, credentialsResponse] = await Promise.all([
      fetch("/api/vault"),
      fetch("/api/manage/vault/credentials")
    ]);
    if (!vaultResponse.ok || !credentialsResponse.ok) throw new Error("Vault request failed.");
    const vault = await vaultResponse.json();
    const credentialData = await credentialsResponse.json();
    const entries = new Map();
    (vault.created_accounts || []).forEach((account) => {
      entries.set(`${account.service}\u0000${account.username}`, {
        service: account.service,
        username: account.username,
        timestamp: account.timestamp || ""
      });
    });
    (credentialData.credentials || []).forEach((credential) => {
      entries.set(`${credential.service}\u0000${credential.username}`, credential);
    });
    const allEntries = [...entries.values()];

    if (allEntries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No credentials stored in vault yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    allEntries.forEach(item => {
      const tr = document.createElement("tr");
      const serviceCell = document.createElement("td");
      const serviceBadge = document.createElement("span");
      serviceBadge.className = "badge-tag cyan";
      serviceBadge.textContent = `${item.service}${item.status === "draft" ? " · DRAFT" : ""}`;
      serviceCell.appendChild(serviceBadge);
      const usernameCell = document.createElement("td");
      usernameCell.textContent = `👤 ${item.username}`;
      const secretCell = document.createElement("td");
      const secretText = document.createElement("code");
      secretText.textContent = "Hidden";
      const revealButton = document.createElement("button");
      revealButton.className = "btn-sm";
      revealButton.textContent = "Reveal";
      revealButton.disabled = !credentialData.credentials.some(
        (credential) => credential.service === item.service && credential.username === item.username
      );
      revealButton.addEventListener("click", () => revealVaultSecret(item, secretText, revealButton));
      secretCell.append(secretText, document.createTextNode(" "), revealButton);
      const timestampCell = document.createElement("td");
      timestampCell.textContent = item.timestamp ? new Date(item.timestamp).toLocaleString() : "--";
      const actionsCell = document.createElement("td");
      const deleteButton = document.createElement("button");
      deleteButton.className = "btn-danger-sm";
      deleteButton.textContent = "Delete";
      deleteButton.addEventListener("click", () => deleteVaultEntry(item.service, item.username));
      actionsCell.appendChild(deleteButton);
      tr.append(serviceCell, usernameCell, secretCell, timestampCell, actionsCell);
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Error loading vault: ${e}</td></tr>`;
  }
}

async function revealVaultSecret(item, secretText, button) {
  if (button.dataset.revealed === "true") {
    secretText.textContent = "Hidden";
    button.textContent = "Reveal";
    button.dataset.revealed = "false";
    return;
  }
  try {
    const response = await fetch("/api/manage/vault/credential/reveal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service: item.service, username: item.username })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not reveal the credential.");
    secretText.textContent = data.secret;
    button.textContent = "Hide";
    button.dataset.revealed = "true";
  } catch (error) {
    showToast(`Unable to reveal credential: ${error.message}`);
  }
}

async function deleteVaultEntry(service, username) {
  if (!confirm(`Delete credential for ${service} (${username})?`)) return;
  try {
    const res = await fetch(`/api/manage/vault/credential?service=${encodeURIComponent(service)}&username=${encodeURIComponent(username)}`, {
      method: "DELETE"
    });
    if (res.ok) {
      showToast(`Deleted ${service} credential`);
      loadVaultTable();
    } else {
      showToast("Failed to delete credential");
    }
  } catch (e) {
    showToast("Error deleting credential: " + e);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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
    const isBrowserClick = domainText.includes("browser");
    const confirmed = !isBrowserClick || confirm("Click this browser location? It may submit, purchase, or book.");
    if (!confirmed) return;

    showToast(`Dispatching Direct Click at (${normX}, ${normY}) on ${domainText}`);

    try {
      const res = await fetch("/api/interact/click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          x: normX,
          y: normY,
          domain: isBrowserClick ? "browser" : "desktop",
          confirmed
        })
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

function setupUIActions() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;

    if (action === "switch-tab") switchHubTab(button.dataset.tab);
    else if (action === "toggle-browser-mode") toggleBrowserVisibility();
    else if (action === "logout") logout();
    else if (action === "submit-goal") submitGoal();
    else if (action === "toggle-pause") togglePause();
    else if (action === "abort-goal") abortGoal();
    else if (action === "approve-action") decideApproval(true);
    else if (action === "reject-action") decideApproval(false);
    else if (action === "queue-mission") queueMission();
    else if (action === "browser-navigate") directNavigate();
    else if (action === "browser-action") directBrowserAction(button.dataset.browserAction, button.dataset.target || null);
    else if (action === "clear-logs") clearLogs();
    else if (action === "refresh-workspace") loadWorkspaceTree();
    else if (action === "save-file") saveActiveFile();
    else if (action === "delete-file") deleteActiveFile();
    else if (action === "refresh-windows") loadWindowsList();
    else if (action === "refresh-processes") loadProcessList();
    else if (action === "refresh-mobile") loadMobileDetails();
    else if (action === "mobile-key") sendMobileKey(Number(button.dataset.keycode));
    else if (action === "scan-mobile-otp") scanMobileOTP();
    else if (action === "refresh-vault") loadVaultTable();
    else if (action === "focus-window") focusWindow(Number(button.dataset.hwnd));
    else if (action === "close-window") closeWindow(Number(button.dataset.hwnd));
  });

  document.getElementById("preset-selector").addEventListener("change", (event) => {
    applyPreset(event.target.value);
  });
  document.getElementById("browser-url-bar").addEventListener("keydown", (event) => {
    if (event.key === "Enter") directNavigate();
  });
}

window.addEventListener("DOMContentLoaded", () => {
  setupUIActions();
  initApp();
  setupInteractiveViewport();
});
