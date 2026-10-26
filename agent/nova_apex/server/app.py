import asyncio
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

# Mount Static UI
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(STATIC_DIR / "index.html"))
