# ⚡ NOVA-APEX // Universal Autonomous Automation OS

> **Production-Grade Next-Gen Cross-Platform Computer-Use & Web Automation Agent System**  
> Operates across **Web Browsers (Playwright Stealth)**, **Desktop GUI (Windows / PyAutoGUI)**, **Mobile Devices (Android ADB)**, and **Terminal Shell**.

---

## 🌟 Key Capabilities

### 1. 🌐 Autonomous Web & Internet Engine
- **Stealth Playwright Automation:** Automated Chromium browser with bot-evasion fingerprints, stealth webdriver masking, and human typing cadence.
- **Auto Account Creation & Form Filling:** Automatically scans DOM for registration inputs (`email`, `username`, `password`, `terms`), synthesizes persona credentials, fills inputs, and clicks submit.
- **Visual Verification & Snapshots:** Real-time DOM extraction, accessibility tree grounding, and full-page viewport screenshots.
- **Credential Vault Integration:** Automatically persists generated credentials, tokens, and cookies to `data/artifacts/agent_memory_vault.json`.

### 2. 🖥️ Desktop OS & Computer-Use Engine
- **GUI Interaction:** Precise mouse moves, single/double clicks, drags, and keystrokes with hardware-level failsafe protection.
- **Multimodal Visual Grounding:** Captures desktop state snapshots for AI vision models.
- **Complete Filesystem Manipulation:** Creates folders, reads/writes code files, generates project scaffolds, and searches workspace directories.

### 3. 📱 Mobile Device Engine (Android ADB)
- **Auto-Discovery:** Automatically detects connected Android physical devices and emulators over USB or TCP/IP.
- **Remote Mobile Control:** ADB tap, swipe gestures, text input, and hardware keyevents (Home, Back, Enter, App Switcher).
- **UI Automator Dump:** Pulls mobile XML hierarchy dumps and direct frame buffer screenshots.

### 4. 🧠 Autonomous Cognitive Architecture
- **Hierarchical Planner:** Converts high-level natural language prompts into executable DAG milestone graphs.
- **Dynamic Self-Healing:** Catches runtime failures and automatically invokes the replanner to synthesize alternate paths.
- **Dual-Tier Memory System:** Short-term scratchpad with variable expansion (`${username}`, `${password}`) + Persistent Long-term Knowledge Vault.
- **Multi-Model Provider:** Built-in support for Google Gemini, OpenAI (GPT-4o), Anthropic Claude, Ollama, and an Autonomous Heuristic Engine fallback.

### 5. 🎛️ Real-Time Mission Control Web Dashboard
- Cybernetic dark glassmorphic UI running on FastAPI & WebSockets.
- Live stream of agent thinking, perception viewport, step milestone graphs, and account vault.

---

## 🚀 Quick Start Guide

### 1. Activate Environment & Run Web Dashboard
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Launch Mission Control Web UI
python main.py --server --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

### 2. Run Interactive Terminal CLI
```powershell
python main.py
```

### 3. Direct Headless Mission Execution
```powershell
# Create an automated account on GitHub
python main.py --account-url "https://github.com/signup"

# Execute a complex multi-domain goal
python main.py --goal "Scaffold fullstack app, create folders and files, capture desktop screenshot"
```

---

## 📁 System Architecture

```
agent/
├── nova_apex/
│   ├── config/
│   │   └── settings.py              # Environment configuration & directory bindings
│   ├── core/
│   │   ├── engine.py                # Main Autonomous Orchestration Loop
│   │   ├── planner.py               # Hierarchical Planner & Self-Healing Replanner
│   │   ├── memory.py                # Dual-tier working memory & credential vault
│   │   ├── llm_provider.py          # Multi-LLM provider & Heuristic fallback
│   │   ├── logger.py                # Rich console & real-time WebSocket logger
│   │   └── schemas.py               # Pydantic schemas (ActionRequest, StepResult, PlanStep)
│   ├── controllers/
│   │   ├── browser_controller.py    # Stealth Playwright browser automation
│   │   ├── desktop_controller.py    # PyAutoGUI OS automation & filesystem operations
│   │   ├── mobile_controller.py     # Android ADB mobile automation
│   │   └── shell_controller.py      # PowerShell / Subprocess command runner
│   ├── skills/
│   │   ├── web_account_creator.py   # Multi-stage automated web registration
│   │   ├── doc_generator.py         # Autonomous code & document generator
│   │   ├── system_admin.py          # System telemetry & disk cleanup
│   │   └── research_agent.py        # Autonomous deep web scraper & researcher
│   ├── server/
│   │   ├── app.py                   # FastAPI REST API & WebSocket endpoints
│   │   ├── ws_manager.py            # Live real-time WebSocket pub/sub
│   │   └── static/                  # Mission Control Web Dashboard (HTML/CSS/JS)
│   └── cli.py                       # Terminal rich interactive CLI
├── data/
│   ├── artifacts/                   # Saved screenshots, reports, and credential vault
│   └── logs/                        # Structured JSONL session audit traces
├── workspace/                       # Safe isolated user workspace directory
├── main.py                          # Unified launcher
├── requirements.txt                 # Dependencies manifest
└── .env                             # Configuration & API keys
```

---

## ⚙️ Configuration (`.env`)

```ini
# LLM Providers (Optional: system works out-of-the-box with heuristic engine)
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

DEFAULT_LLM_PROVIDER=auto
DEFAULT_MODEL=gemini-2.5-flash

# Browser Settings
BROWSER_HEADLESS=false
BROWSER_STEALTH=true
BROWSER_VIEWPORT_WIDTH=1280
BROWSER_VIEWPORT_HEIGHT=800

# Mobile Settings (ADB)
ADB_ENABLED=true

# Server Settings
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```
