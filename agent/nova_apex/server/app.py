import os
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GoalRequest(BaseModel):
    prompt: str

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

@app.get("/api/vault")
async def get_vault():
    return {
        "created_accounts": agent_memory.vault.get("created_accounts", []),
        "saved_entities": agent_memory.vault.get("saved_entities", {})
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

class BrowserNavigateRequest(BaseModel):
    url: str
    headless: Optional[bool] = None

class BrowserActionRequest(BaseModel):
    action: str
    target: Optional[str] = None
    value: Optional[str] = None

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
    action_type = ActionType(req.action.lower()) if req.action.lower() in [a.value for a in ActionType] else ActionType.CLICK_ELEMENT
    res = await browser_controller.execute_action(ActionRequest(
        domain=ActionDomain.BROWSER,
        action_type=action_type,
        description=f"Direct action {req.action}",
        target=req.target,
        value=req.value
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
        from nova_apex.controllers.browser_controller import browser_controller
        if browser_controller.page:
            await browser_controller.human_mouse_move(req.x, req.y)
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
    file_path = settings.artifacts_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(str(file_path))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send current logs history immediately on connection
        for entry in agent_logger.history[-50:]:
            await websocket.send_json(entry)
        while True:
            # Keep alive / receive client events
            await websocket.receive_text()
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
    target = settings.workspace_dir / path
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
    target = settings.workspace_dir / req.path
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(req.content)
    return {"success": True, "path": req.path, "bytes": len(req.content)}

@app.delete("/api/manage/workspace/file")
async def delete_workspace_file(path: str):
    target = settings.workspace_dir / path
    if target.exists():
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            import shutil
            shutil.rmtree(target)
        return {"success": True, "deleted": path}
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

    target = devices[0]
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
    keycode: int

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
        return {"count": len(cookies), "cookies": cookies[:50]}
    except Exception:
        return {"cookies": []}

# 5. Vault CRUD Management
class CredentialItem(BaseModel):
    service: str
    username: str
    secret: str
    extra: Dict[str, Any] = {}

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
    agent_memory.save()
    return {"success": True, "service": service, "username": username}

# Mount Static UI
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(STATIC_DIR / "index.html"))
