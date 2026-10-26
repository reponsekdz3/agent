# NOVA-APEX — Local-first computer-use agent

NOVA-APEX is a Python agent for user-directed browser, desktop, filesystem, Android ADB, and shell workflows. Its planner can use supported hosted or local language-model providers, while the FastAPI Mission Control dashboard reports mission progress.

This project is under active hardening. Treat it as a local automation tool, not as a production-hardened remote agent. **Do not expose Mission Control to the public internet.** Keep the dashboard bound to loopback and use an isolated machine or VM for high-impact automation.

## Design principles

- **Human control:** the agent prepares actions and reports outcomes; site signup, legal consent, account verification, payments, and other sensitive confirmation steps remain with the user.
- **Safe defaults:** shell commands and destructive filesystem actions are disabled unless explicitly enabled in a local .env.
- **Workspace boundaries:** file creation, reading, and deletion must resolve inside the configured workspace.
- **Secret minimization:** the persistent vault stores metadata only. Secrets use the OS credential manager when available; if it is unavailable, secret values stay in process memory and are lost when the process exits.
- **No session by default:** browser cookies/session state are neither loaded nor persisted unless BROWSER_PERSIST_SESSION=true is explicitly chosen.
- **Visible, standard automation:** Playwright uses normal browser behavior rather than browser-fingerprint spoofing or anti-bot evasion.
- **Honest completion:** an empty plan or a planner error is a failed mission, not a successful one.

## Requirements

- Python 3.11 or newer
- A model API key for hosted reasoning, or an Ollama service and locally available model
- Playwright browser installation for browser workflows
- Windows for native GUI controls; Android SDK Platform Tools for ADB actions

## Setup (Windows PowerShell)

From the repository root:

~~~powershell
cd .\agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
playwright install chromium
~~~

Edit .env locally and add the model provider key you intend to use. Never commit .env, browser-session state, screenshots, logs, or vault data.

## Run Mission Control

~~~powershell
python main.py --server --port 8000
~~~

Open <http://127.0.0.1:8000>. The API defaults to loopback-only access, checks Host and browser Origin, and disables credentials in CORS. Do not set SERVER_HOST=0.0.0.0 or tunnel this dashboard to an untrusted network.

## Run a mission from the CLI

~~~powershell
python main.py
python main.py --goal "Open https://example.com and summarize the page"
~~~

For model configuration, set DEFAULT_LLM_PROVIDER to auto, gemini, openai, anthropic, or ollama. Configure the corresponding API key or local service. When no provider is available, a limited heuristic planner is used; it is not a substitute for model reasoning or verification.

## High-impact permissions

These switches are deliberately off by default:

~~~dotenv
ALLOW_SHELL_EXECUTION=false
ALLOW_DESTRUCTIVE_ACTIONS=false
~~~

Only enable them on a machine you control after reviewing the goal and commands. Enabling shell execution allows the agent to run commands with the current user's operating-system permissions. The workspace restriction is not a sandbox for shell commands. Use a VM or container with restricted permissions for untrusted tasks.

The browser signup helper fills only details the user provides and stops for review. It does not synthesize a pretend identity, accept terms, submit the form, or retrieve OTP/2FA codes. Enter verification codes directly into the intended service.

## Architecture

- nova_apex/core/engine.py: mission lifecycle, execution, pause/abort handling
- nova_apex/core/planner.py and llm_provider.py: plan creation and model adapters
- nova_apex/core/memory.py: transient working state and metadata-only vault
- nova_apex/security.py: canonical workspace path resolution
- nova_apex/controllers/: Playwright, Windows desktop/filesystem, ADB and shell adapters
- nova_apex/server/: local FastAPI API, WebSocket telemetry, static Mission Control UI
- nova_apex/skills/: research, scaffolding, signup preparation and system telemetry helpers
- tests/test_safety.py: non-destructive security and regression checks

## Checks

Run unit tests from this directory:

~~~powershell
python -m pytest -q tests/test_safety.py
~~~

The legacy files test_system.py and test_low_level.py perform live browser/desktop/device operations and are not suitable for ordinary CI. Run them only on a dedicated test machine after inspecting the actions.

## Security notes and recovery

If an earlier version of this repository was used with real credentials, rotate any credential that may have been saved in the old JSON vault. Removing a file from the current branch does not remove it from Git history. Also revoke the browser session that was previously stored in data/browser_profiles/storage_state.json. The new secret-handling code migrates a legacy vault to metadata-only storage when it starts, but repository history must be handled separately if sensitive values were committed.

This codebase is not yet a multi-user, internet-facing service. Before such a deployment, add authenticated identity, role-based/object-level authorization, encrypted secret management, an isolated worker execution model, rate limits, structured audit retention, and deployment-specific security review.
