// Same-origin request helper: mutation requests carry a per-app marker.
async function apiFetch(input, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("X-Nova-Apex-Request", "1");
  return window.fetch(input, { ...init, headers, credentials: "same-origin" });
}

// NOVA-APEX Mission Control Dynamic Client Engine
let socket = null;
let isPaused = false;
let isHeaded = false;

// Presets dictionary
const PRESETS = {
  navigate_github: "Launch browser and navigate to https://github.com, inspect the page DOM, and capture high-res verification screenshot.",
  create_account: "Open a signup page selected by the user, fill only details the user provides, and stop for manual review. Never auto-submit a form or process verification codes.",
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
    const res = await apiFetch("/api/goal", {
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
    const res = await apiFetch(endpoint, { method: "POST" });
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
      await apiFetch("/api/abort", { method: "POST" });
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
    const res = await apiFetch("/api/browser/navigate", {
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
    const res = await apiFetch("/api/browser/action", {
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
    const res = await apiFetch("/api/browser/toggle-mode", { method: "POST" });
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
    const res = await apiFetch("/api/status");
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

  stepsList.replaceChildren();
  data.steps.forEach(step => {
    const card = document.createElement("div");
    card.className = `step-card ${String(step.status || "pending").replace(/[^a-z_]/g, "")}`;
    const info = document.createElement("div");
    info.className = "step-info";
    const titleLine = document.createElement("div");
    titleLine.className = "step-title-line";
    const number = document.createElement("span");
    number.className = "step-number";
    number.textContent = `#${step.step_id}`;
    const title = document.createElement("span");
    title.className = "step-title";
    title.textContent = String(step.title || "Untitled step");
    titleLine.append(number, title);
    const description = document.createElement("span");
    description.className = "step-desc";
    description.textContent = String(step.description || "");
    info.append(titleLine, description);
    const badge = document.createElement("div");
    badge.className = `step-badge ${String(step.status || "pending").replace(/[^a-z_]/g, "")}`;
    badge.textContent = String(step.status || "pending");
    card.append(info, badge);
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
    const res = await apiFetch("/api/telemetry");
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
    const res = await apiFetch("/api/manage/workspace/tree");
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
    const res = await apiFetch(`/api/manage/workspace/file?path=${encodeURIComponent(path)}`);
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
    const res = await apiFetch("/api/manage/workspace/file", {
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
    const res = await apiFetch(`/api/manage/workspace/file?path=${encodeURIComponent(activeFilePath)}`, {
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
    const res = await apiFetch("/api/manage/windows");
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
          <button class="btn-sm" onclick="focusWindow(${w.hwnd})">🔍 Focus</button>
          <button class="btn-danger-sm" onclick="closeWindow(${w.hwnd})">✕ Close</button>
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
    const res = await apiFetch("/api/manage/windows/focus", {
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
    const res = await apiFetch("/api/manage/windows/close", {
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
    const res = await apiFetch("/api/manage/processes");
    const data = await res.json();
    if (!data.processes || data.processes.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No process data available.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    data.processes.forEach(p => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge-tag green">PID ${p.Id || p.PID || '--'}</span></td>
        <td style="font-weight: 600;">${escapeHtml(p.ProcessName || p.Name || '--')}</td>
        <td>${p.MemoryMB || '--'} MB</td>
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
    const res = await apiFetch("/api/manage/mobile/info");
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
      <div class="mobile-info-item">
        <span>Device ID:</span>
        <span class="badge-tag cyan">${data.device_id || '--'}</span>
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
  } catch (e) {
    card.innerHTML = `<div class="empty-state">ADB query error: ${e}</div>`;
  }
}

async function sendMobileKey(keycode) {
  showToast(`Dispatching ADB Keycode: ${keycode}...`);
  try {
    const res = await apiFetch("/api/manage/mobile/keyevent", {
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
  if (!box) return;
  box.textContent = "For security, NOVA-APEX does not read, display, or relay verification codes. Enter the code directly into the intended service.";
  showToast("Automatic OTP extraction is disabled.");
}

// 4. Credential Vault Management
async function loadVaultTable() {
  const tbody = document.getElementById("vault-table-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Querying secure vault...</td></tr>`;

  try {
    const res = await apiFetch("/api/vault");
    const data = await res.json();
    const creds = data.credentials || [];
    const accounts = data.created_accounts || [];

    const allEntries = [...creds];
    accounts.forEach(acc => {
      if (!allEntries.some(c => c.service === acc.service && c.username === acc.username)) {
        allEntries.push({
          service: acc.service,
          username: acc.username,
          secret: acc.password || "••••••••",
          timestamp: acc.timestamp || new Date().toISOString()
        });
      }
    });

    if (allEntries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No credentials stored in vault yet.</td></tr>`;
      return;
    }

    tbody.replaceChildren();
    allEntries.forEach(item => {
      const tr = document.createElement("tr");
      const serviceCell = document.createElement("td");
      const serviceBadge = document.createElement("span");
      serviceBadge.className = "badge-tag cyan";
      serviceBadge.textContent = String(item.service || "");
      serviceCell.appendChild(serviceBadge);
      const userCell = document.createElement("td");
      userCell.style.fontWeight = "600";
      userCell.textContent = `👤 ${String(item.username || "")}`;
      const secretCell = document.createElement("td");
      const secretCode = document.createElement("code");
      secretCode.textContent = "••••••••";
      secretCell.appendChild(secretCode);
      const timeCell = document.createElement("td");
      timeCell.style.color = "var(--text-muted)";
      timeCell.style.fontSize = "10px";
      timeCell.textContent = item.timestamp ? new Date(item.timestamp).toLocaleString() : "--";
      const actionCell = document.createElement("td");
      const deleteButton = document.createElement("button");
      deleteButton.className = "btn-danger-sm";
      deleteButton.textContent = "🗑️ Delete";
      deleteButton.addEventListener("click", () => deleteVaultEntry(String(item.service || ""), String(item.username || "")));
      actionCell.appendChild(deleteButton);
      tr.append(serviceCell, userCell, secretCell, timeCell, actionCell);
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Error loading vault: ${e}</td></tr>`;
  }
}

async function deleteVaultEntry(service, username) {
  if (!confirm(`Delete credential for ${service} (${username})?`)) return;
  try {
    const res = await apiFetch(`/api/manage/vault/credential?service=${encodeURIComponent(service)}&username=${encodeURIComponent(username)}`, {
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

    showToast(`Dispatching Direct Click at (${normX}, ${normY}) on ${domainText}`);

    try {
      const res = await apiFetch("/api/interact/click", {
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
