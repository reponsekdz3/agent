import os
import re
import asyncio
import hmac
import ipaddress
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from nova_apex.config.settings import settings
from nova_apex.core.engine import engine
from nova_apex.core.logger import agent_logger
from nova_apex.core.memory import agent_memory
from nova_apex.core.schemas import ActionDomain, ActionType, ActionRequest
from nova_apex.skills.system_admin import system_admin
from nova_apex.server.ws_manager import ws_manager

app = FastAPI(
    title="NOVA-APEX Universal Automation OS",
    description="Cross-platform Autonomous Computer-Use & Web Automation Engine",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

AUTH_COOKIE_NAME = "nova_apex_session"
_auth_sessions: Dict[str, Dict[str, Any]] = {}
_failed_logins: Dict[str, list[float]] = {}

class GoalRequest(BaseModel):
    prompt: str

class LoginRequest(BaseModel):
    password: str

class CredentialLookupRequest(BaseModel):
    service: str
    username: str

def resolve_workspace_path(relative_path: str) -> Path:
    root = settings.workspace_dir.resolve()
    requested = Path(relative_path)
    if requested.is_absolute():
        raise HTTPException(status_code=400, detail="Workspace paths must be relative.")
    resolved = (root / requested).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path must remain inside the workspace.")
    return resolved

def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

def _get_session(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    session = _auth_sessions.get(session_id)
    if not session:
        return None
    if session["expires_at"] <= time.time():
        _auth_sessions.pop(session_id, None)
        return None
    return session

def _origin_matches_host(origin: Optional[str], host: Optional[str]) -> bool:
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == (host or "").lower()
    except ValueError:
        return False

@app.on_event("startup")
async def enforce_safe_bind_configuration():
    if not settings.auth_password:
        raise RuntimeError(
            "NOVA_APEX_AUTH_PASSWORD is required for dashboard access, including loopback use."
        )
    if settings.auth_password and len(settings.auth_password) < 16:
        raise RuntimeError("NOVA_APEX_AUTH_PASSWORD must contain at least 16 characters.")
    if settings.auth_password and not _is_loopback_host(settings.server_host) and not settings.auth_cookie_secure:
        raise RuntimeError("NOVA_APEX_COOKIE_SECURE=true is required for authenticated non-loopback access.")
    if settings.auth_password and os.name != "nt":
        raise RuntimeError("Authenticated remote control currently requires Windows DPAPI vault protection.")
    if settings.auth_session_ttl_seconds < 60:
        raise RuntimeError("NOVA_APEX_SESSION_TTL_SECONDS must be at least 60 seconds.")

@app.middleware("http")
async def protect_control_api(request: Request, call_next):
    path = request.url.path
    is_auth_endpoint = path in {"/api/auth/status", "/api/auth/login"}
    response = None

    if path.startswith("/api/") and not is_auth_endpoint:
        origin = request.headers.get("origin")
        if not _origin_matches_host(origin, request.headers.get("host")):
            response = JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)

        elif not settings.auth_password:
            response = JSONResponse({"detail": "Dashboard authentication is not configured."}, status_code=503)

        else:
            session = _get_session(request.cookies.get(AUTH_COOKIE_NAME))
            if not session:
                response = JSONResponse({"detail": "Authentication required."}, status_code=401)
            else:
                request.state.auth_session = session

            if response is None and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                csrf_token = request.headers.get("x-csrf-token", "")
                if not hmac.compare_digest(csrf_token, session["csrf_token"]):
                    response = JSONResponse({"detail": "A valid CSRF token is required."}, status_code=403)

    if response is None:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self' ws: wss:; "
        "worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/api/auth/status")
async def get_auth_status(request: Request):
    if not settings.auth_password:
        return {"required": True, "authenticated": False, "csrf_token": None}
    session = _get_session(request.cookies.get(AUTH_COOKIE_NAME))
    return {
        "required": True,
        "authenticated": session is not None,
        "csrf_token": session["csrf_token"] if session else None
    }

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    if not _origin_matches_host(request.headers.get("origin"), request.headers.get("host")):
        raise HTTPException(status_code=403, detail="Cross-origin login is not allowed.")
    if not settings.auth_password:
        raise HTTPException(status_code=503, detail="Configure NOVA_APEX_AUTH_PASSWORD before starting the dashboard.")
    client_host = request.client.host if request.client else "unknown"
    now = time.time()
    recent_failures = [stamp for stamp in _failed_logins.get(client_host, []) if now - stamp < 900]
    if len(recent_failures) >= 5:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in 15 minutes.")
    if not hmac.compare_digest(req.password, settings.auth_password):
        recent_failures.append(now)
        _failed_logins[client_host] = recent_failures
        raise HTTPException(status_code=401, detail="Invalid password.")

    if len(_auth_sessions) >= 2048:
        for session_key, session in list(_auth_sessions.items()):
            if session["expires_at"] <= now:
                _auth_sessions.pop(session_key, None)
        if len(_auth_sessions) >= 2048:
            raise HTTPException(status_code=503, detail="Session capacity reached. Try again later.")

    _failed_logins.pop(client_host, None)
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    _auth_sessions[session_id] = {
        "csrf_token": csrf_token,
        "expires_at": time.time() + settings.auth_session_ttl_seconds
    }
    response = JSONResponse({"authenticated": True, "csrf_token": csrf_token})
    response.set_cookie(
        AUTH_COOKIE_NAME,
        session_id,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/"
    )
    return response

@app.post("/api/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get(AUTH_COOKIE_NAME)
    if session_id:
        _auth_sessions.pop(session_id, None)
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/", httponly=True, secure=settings.auth_cookie_secure, samesite="strict")
    return response

@app.get("/api/status")
async def get_status():
    return engine.get_status()

@app.post("/api/goal")
async def submit_goal(req: GoalRequest, background_tasks: BackgroundTasks):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Goal prompt cannot be empty.")

    # Run engine in background task
    background_tasks.add_task(engine.run_goal, req.prompt)
    return {"message": "Goal accepted and scheduled for execution.", "prompt": req.prompt}

@app.post("/api/pause")
async def pause_agent():
    engine.pause()
    return {"status": "paused"}

@app.post("/api/resume")
async def resume_agent():
    engine.resume()
    return {"status": "resumed"}

@app.post("/api/abort")
async def abort_agent():
    engine.abort()
    return {"status": "aborted"}

@app.post("/api/approval/approve")
async def approve_pending_action():
    if not engine.approve_pending_action():
        raise HTTPException(status_code=409, detail="There is no pending action to approve.")
    return {"status": "approved"}

@app.post("/api/approval/reject")
async def reject_pending_action():
    if not engine.reject_pending_action():
        raise HTTPException(status_code=409, detail="There is no pending action to reject.")
    return {"status": "rejected"}

@app.get("/api/vault")
async def get_vault():
    return {
        "created_accounts": agent_memory.vault.get("created_accounts", []),
        "saved_entities": {
            key: {"updated_at": value.get("updated_at")}
            for key, value in agent_memory.vault.get("saved_entities", {}).items()
        }
    }

@app.get("/api/telemetry")
async def get_telemetry():
    return system_admin.get_system_telemetry()

@app.get("/api/system/windows")
async def get_open_windows():
    from nova_apex.controllers.desktop_controller import desktop_controller
    return {"windows": desktop_controller.list_open_windows()}

@app.get("/api/system/devices")
async def get_mobile_devices():
    from nova_apex.controllers.mobile_controller import mobile_controller
    return {"devices": mobile_controller.get_connected_devices()}

class DirectClickRequest(BaseModel):
    x: int
    y: int
    domain: str = "desktop"
    confirmed: bool = False

class BrowserNavigateRequest(BaseModel):
    url: str
    headless: Optional[bool] = None

class BrowserActionRequest(BaseModel):
    action: str
    target: Optional[str] = None
    value: Optional[str] = None
    email: Optional[str] = None
    confirmed: bool = False

@app.post("/api/browser/navigate")
async def browser_navigate(req: BrowserNavigateRequest):
    from nova_apex.controllers.browser_controller import browser_controller
    if req.headless is not None:
        settings.browser_headless = req.headless
        if browser_controller._is_initialized:
            await browser_controller.close()

    res = await browser_controller.execute_action(ActionRequest(
        domain=ActionDomain.BROWSER,
        action_type=ActionType.NAVIGATE,
        description=f"Direct navigate to {req.url}",
        target=req.url
    ))
    return {
        "success": res.success,
        "output": res.output,
        "screenshot": res.screenshot_path,
        "data": res.data,
        "error": res.error
    }

@app.post("/api/browser/action")
async def browser_direct_action(req: BrowserActionRequest):
    from nova_apex.controllers.browser_controller import browser_controller
    try:
        action_type = ActionType(req.action.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported browser action: {req.action}")
    allowed_actions = {
        ActionType.NAVIGATE,
        ActionType.CLICK_ELEMENT,
        ActionType.TYPE_ELEMENT,
        ActionType.EXTRACT_CONTENT,
        ActionType.BROWSER_SCREENSHOT,
        ActionType.SUBMIT_FORM,
        ActionType.CREATE_ACCOUNT,
        ActionType.EVALUATE_JS,
        ActionType.SWITCH_TAB,
        ActionType.CLOSE_BROWSER
    }
    if action_type not in allowed_actions:
        raise HTTPException(status_code=400, detail=f"Action {req.action} is not a browser action.")
    if action_type in {
        ActionType.CLICK_ELEMENT,
        ActionType.SUBMIT_FORM,
        ActionType.EVALUATE_JS
    } and not req.confirmed:
        raise HTTPException(status_code=428, detail="This action requires explicit confirmation.")
    res = await browser_controller.execute_action(ActionRequest(
        domain=ActionDomain.BROWSER,
        action_type=action_type,
        description=f"Direct action {req.action}",
        target=req.target,
        value=req.value,
        params={"user_confirmed": req.confirmed, "email": req.email}
    ))
    return {
        "success": res.success,
        "output": res.output,
        "screenshot": res.screenshot_path,
        "error": res.error
    }

@app.post("/api/browser/toggle-mode")
async def toggle_browser_mode():
    from nova_apex.controllers.browser_controller import browser_controller
    settings.browser_headless = not settings.browser_headless
    mode_str = "Headless (Background)" if settings.browser_headless else "Headed (Visible on Desktop)"
    agent_logger.info(f"Browser mode toggled to: {mode_str}", domain="BROWSER")
    if browser_controller._is_initialized:
        await browser_controller.close()
    return {"headless": settings.browser_headless, "mode": mode_str}

@app.post("/api/interact/click")
async def direct_click(req: DirectClickRequest):
    if req.domain == "browser":
        if not req.confirmed:
            raise HTTPException(status_code=428, detail="Browser clicks require explicit confirmation.")
        from nova_apex.controllers.browser_controller import browser_controller
        if browser_controller.page:
            await browser_controller.move_mouse(req.x, req.y)
            await browser_controller.page.mouse.click(req.x, req.y)
            shot = await browser_controller.take_screenshot("interactive_click")
            return {"success": True, "screenshot": shot}
    else:
        from nova_apex.controllers.desktop_controller import desktop_controller
        shot = desktop_controller.execute_action(ActionRequest(
            domain=ActionDomain.DESKTOP,
            action_type=ActionType.DESKTOP_CLICK,
            description="User interactive viewport click",
            target=f"{req.x},{req.y}"
        ))
        return {"success": shot.success, "screenshot": shot.screenshot_path}

@app.get("/api/artifacts/{filename}")
async def get_artifact(filename: str):
    artifact_root = settings.artifacts_dir.resolve()
    file_path = (artifact_root / filename).resolve()
    if file_path.parent != artifact_root or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(str(file_path))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not _origin_matches_host(websocket.headers.get("origin"), websocket.headers.get("host")):
        await websocket.close(code=1008)
        return
    if not settings.auth_password or not _get_session(websocket.cookies.get(AUTH_COOKIE_NAME)):
        await websocket.close(code=1008)
        return
    await ws_manager.connect(websocket)
    try:
        # Send current logs history immediately on connection
        for entry in agent_logger.history[-50:]:
            await websocket.send_json(entry)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                if settings.auth_password and not _get_session(websocket.cookies.get(AUTH_COOKIE_NAME)):
                    await websocket.close(code=1008)
                    return
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# =========================================================================
# CENTRAL OMNI MANAGEMENT HUB API ROUTES
# =========================================================================

# 1. Workspace File Explorer Management
@app.get("/api/manage/workspace/tree")
async def get_workspace_tree():
    workspace = settings.workspace_dir
    items = []
    for root, dirs, files in os.walk(workspace):
        rel_root = os.path.relpath(root, workspace)
        for d in dirs:
            items.append({
                "name": d,
                "type": "directory",
                "path": os.path.normpath(os.path.join(rel_root, d)).replace("\\", "/")
            })
        for f in files:
            full_p = Path(root) / f
            items.append({
                "name": f,
                "type": "file",
                "path": os.path.normpath(os.path.join(rel_root, f)).replace("\\", "/"),
                "size": full_p.stat().st_size if full_p.exists() else 0,
                "modified": datetime.fromtimestamp(full_p.stat().st_mtime).isoformat() if full_p.exists() else ""
            })
    return {"workspace": str(workspace), "items": items}

@app.get("/api/manage/workspace/file")
async def get_workspace_file(path: str):
    target = resolve_workspace_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in workspace")
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": path, "content": content, "size": len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SaveFileRequest(BaseModel):
    path: str
    content: str

@app.post("/api/manage/workspace/file")
async def save_workspace_file(req: SaveFileRequest):
    target = resolve_workspace_path(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(req.content)
    return {"success": True, "path": req.path, "bytes": len(req.content)}

@app.delete("/api/manage/workspace/file")
async def delete_workspace_file(path: str):
    target = resolve_workspace_path(path)
    if target.exists():
        if target.is_file():
            target.unlink()
            return {"success": True, "deleted": path}
        raise HTTPException(status_code=400, detail="Only workspace files can be deleted through this endpoint.")
    raise HTTPException(status_code=404, detail="Path does not exist")

# 2. Desktop OS Process & Window Management
@app.get("/api/manage/processes")
async def get_running_processes():
    import subprocess, json
    try:
        cmd = "Get-Process | Sort-Object CPU -Descending | Select-Object -First 18 Id, ProcessName, @{Name='MemoryMB';Expression={[math]::Round($_.WorkingSet/1MB, 1)}} | ConvertTo-Json"
        res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=5)
        procs = json.loads(res.stdout) if res.stdout.strip() else []
        if isinstance(procs, dict):
            procs = [procs]
        return {"processes": procs}
    except Exception as e:
        return {"processes": [], "error": str(e)}

class WindowActionRequest(BaseModel):
    hwnd: int
    title: Optional[str] = None

@app.post("/api/manage/windows/focus")
async def focus_window_api(req: WindowActionRequest):
    from nova_apex.controllers.desktop_controller import user32
    if user32 and req.hwnd:
        user32.ShowWindow(req.hwnd, 9) # SW_RESTORE
        user32.SetForegroundWindow(req.hwnd)
        return {"success": True, "hwnd": req.hwnd}
    return {"success": False, "error": "Invalid HWND or Win32 unavailable"}

@app.post("/api/manage/windows/close")
async def close_window_api(req: WindowActionRequest):
    from nova_apex.controllers.win32_native import win32_subsystem
    if req.hwnd:
        # WM_CLOSE = 0x0010
        win32_subsystem.send_direct_window_message(req.hwnd, 0x0010)
        return {"success": True, "closed_hwnd": req.hwnd}
    return {"success": False}

# 3. Mobile Device Management
@app.get("/api/manage/mobile/info")
async def get_mobile_detailed_info():
    from nova_apex.controllers.mobile_controller import mobile_controller
    devices = mobile_controller.get_connected_devices()
    if not devices:
        return {"connected": False, "devices": []}

    target = mobile_controller.active_device if mobile_controller.active_device in devices else devices[0]
    bin_p = mobile_controller.adb_bin
    details = {"connected": True, "device_id": target, "devices": devices}
    try:
        import subprocess
        # Get Model
        m_res = subprocess.run([bin_p, "-s", target, "shell", "getprop", "ro.product.model"], capture_output=True, text=True, timeout=3)
        details["model"] = m_res.stdout.strip()
        # Get Android OS version
        v_res = subprocess.run([bin_p, "-s", target, "shell", "getprop", "ro.build.version.release"], capture_output=True, text=True, timeout=3)
        details["android_version"] = v_res.stdout.strip()
        # Get Battery
        b_res = subprocess.run([bin_p, "-s", target, "shell", "dumpsys", "battery"], capture_output=True, text=True, timeout=3)
        level_match = re.search(r"level:\s*(\d+)", b_res.stdout)
        details["battery_level"] = int(level_match.group(1)) if level_match else None
    except Exception as e:
        details["error"] = str(e)
    return details

class MobileKeyRequest(BaseModel):
    keycode: int = Field(ge=0, le=288)

class MobileDeviceSelectionRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=256)

@app.post("/api/manage/mobile/select")
async def select_mobile_device(req: MobileDeviceSelectionRequest):
    from nova_apex.controllers.mobile_controller import mobile_controller
    devices = mobile_controller.get_connected_devices()
    if req.device_id not in devices:
        raise HTTPException(status_code=404, detail="Selected Android device is not currently connected.")
    mobile_controller.active_device = req.device_id
    settings.adb_device_id = req.device_id
    return {"success": True, "device_id": req.device_id}

@app.post("/api/manage/mobile/keyevent")
async def send_mobile_keyevent(req: MobileKeyRequest):
    from nova_apex.controllers.mobile_controller import mobile_controller
    res = mobile_controller.execute_action(ActionRequest(
        domain=ActionDomain.MOBILE,
        action_type=ActionType.ADB_KEYEVENT,
        description=f"Direct keyevent {req.keycode}",
        target=str(req.keycode),
        value=str(req.keycode)
    ))
    return {"success": res.success, "output": res.output}

@app.get("/api/manage/windows")
async def get_manage_windows():
    from nova_apex.controllers.desktop_controller import desktop_controller
    return {"windows": desktop_controller.list_open_windows()}

@app.get("/api/manage/mobile/otp")
async def get_mobile_otp():
    from nova_apex.controllers.mobile_controller import mobile_controller
    devices = mobile_controller.get_connected_devices()
    if not devices:
        return {"connected": False, "otp": None, "message": "No ADB device connected"}
    target = mobile_controller.active_device or devices[0]
    otp = mobile_controller.extract_latest_otp(target)
    return {"connected": True, "device": target, "otp": otp}

# 4. Browser Tabs & Cookies Management
@app.get("/api/manage/browser/tabs")
async def get_browser_tabs():
    from nova_apex.controllers.browser_controller import browser_controller
    if not browser_controller.context:
        return {"tabs": []}
    tabs = []
    for i, p in enumerate(browser_controller.context.pages):
        try:
            tabs.append({
                "index": i,
                "title": await p.title(),
                "url": p.url,
                "is_active": (p == browser_controller.page)
            })
        except Exception:
            pass
    return {"tabs": tabs}

@app.get("/api/manage/browser/cookies")
async def get_browser_cookies():
    from nova_apex.controllers.browser_controller import browser_controller
    if not browser_controller.context:
        return {"cookies": []}
    try:
        cookies = await browser_controller.context.cookies()
        safe_cookies = [
            {key: cookie.get(key) for key in ("name", "domain", "path", "expires", "httpOnly", "secure", "sameSite")}
            for cookie in cookies[:50]
        ]
        return {"count": len(cookies), "cookies": safe_cookies}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unable to inspect browser cookies: {e}") from e

# 5. Vault CRUD Management
class CredentialItem(BaseModel):
    service: str
    username: str
    secret: str
    extra: Dict[str, Any] = Field(default_factory=dict)

@app.get("/api/manage/vault/credentials")
async def list_vault_credentials():
    return {
        "credentials": [
            {
                "service": credential.get("service", ""),
                "username": credential.get("username", ""),
                "timestamp": credential.get("timestamp", ""),
                "status": credential.get("extra", {}).get("status", "stored")
            }
            for credential in agent_memory.vault.get("credentials", [])
        ]
    }

@app.post("/api/manage/vault/credential/reveal")
async def reveal_vault_credential(req: CredentialLookupRequest):
    credential = next(
        (
            item for item in reversed(agent_memory.vault.get("credentials", []))
            if item.get("service") == req.service and item.get("username") == req.username
        ),
        None
    )
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found.")
    agent_logger.info(
        f"Credential explicitly revealed for [{req.service}] as [{req.username}]",
        domain="SECURITY"
    )
    return {"secret": credential.get("secret", "")}

@app.post("/api/manage/vault/credential")
async def add_vault_credential(cred: CredentialItem):
    agent_memory.store_credential(
        service=cred.service,
        username=cred.username,
        secret=cred.secret,
        extra=cred.extra
    )
    return {"success": True, "service": cred.service, "username": cred.username}

@app.delete("/api/manage/vault/credential")
async def delete_vault_credential(service: str, username: str):
    creds = agent_memory.vault.get("credentials", [])
    agent_memory.vault["credentials"] = [
        c for c in creds if not (c.get("service") == service and c.get("username") == username)
    ]
    agent_memory.vault["created_accounts"] = [
        account for account in agent_memory.vault.get("created_accounts", [])
        if not (account.get("service") == service and account.get("username") == username)
    ]
    agent_memory.save()
    return {"success": True, "service": service, "username": username}

# Mount Static UI
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    @app.get("/service-worker.js")
    async def serve_service_worker():
        return FileResponse(
            str(STATIC_DIR / "service-worker.js"),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"}
        )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(STATIC_DIR / "index.html"))
