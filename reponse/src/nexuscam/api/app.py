from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nexuscam.runtime import Runtime
from nexuscam.settings import AppSettings
from nexuscam.types import TransportKind

PHONE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>NexusCam Phone Link</title>
  <style>
    body { font: 16px/1.4 system-ui; background:#061108; color:#d9ffe8; margin:0; padding:16px; }
    button, select { background:#102616; color:#d9ffe8; border:1px solid #2a6; padding:10px 14px; margin:6px 6px 6px 0; }
    video { width:100%; max-height:40vh; background:#000; }
    .ok { color:#1cff7a; }
  </style>
</head>
<body>
  <h1>Phone camera → PC</h1>
  <p>This page streams the phone camera over Wi-Fi or USB tethering. Bluetooth is used only to find this PC.</p>
  <video id="v" autoplay playsinline muted></video>
  <div>
    <select id="facing"><option value="environment">Back camera</option><option value="user">Front camera</option></select>
    <button id="go">Start streaming</button>
    <span id="st"></span>
  </div>
<script>
const st = document.getElementById('st');
document.getElementById('go').onclick = async () => {
  const facing = document.getElementById('facing').value;
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: facing, width: 1280, height: 720 }, audio: false });
  document.getElementById('v').srcObject = stream;
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws/ingress/phone:wifi');
  ws.binaryType = 'arraybuffer';
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const video = document.getElementById('v');
  st.textContent = 'connecting…';
  ws.onopen = () => { st.className = 'ok'; st.textContent = 'live to PC'; };
  ws.onclose = () => { st.textContent = 'disconnected'; };
  const tick = () => {
    if (ws.readyState === 1 && video.videoWidth) {
      canvas.width = video.videoWidth; canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0);
      canvas.toBlob((blob) => { if (blob) blob.arrayBuffer().then((buf) => ws.send(buf)); }, 'image/jpeg', 0.72);
    }
    setTimeout(tick, 66);
  };
  tick();
};
</script>
</body>
</html>
"""


class SourceIn(BaseModel):
    backend: str = Field(examples=["demo", "usb", "pc", "rtsp", "http", "phone"])
    url: str | None = None
    source_id: str | None = None


class ControlIn(BaseModel):
    name: str
    value: float
    source_id: str | None = None


class PtzIn(BaseModel):
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0


class PhoneLinkIn(BaseModel):
    name: str | None = None
    stream_url: str
    transport: str = "wifi_http"
    address: str | None = None


class ViewIn(BaseModel):
    mode: str = Field(examples=["active", "mosaic"])
    source_id: str | None = None


def create_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(title="NexusCam", version="2.0.0")
    static = Path(__file__).resolve().parent.parent / "ui" / "static"
    if static.exists():
        app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        page = static / "index.html"
        if not page.exists():
            return HTMLResponse("<h1>NexusCam</h1><p>UI missing.</p>")
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @app.get("/phone", response_class=HTMLResponse)
    def phone_page():
        return HTMLResponse(PHONE_HTML)

    @app.get("/api/v1/health")
    def health():
        return {"ok": True, "sources": runtime.multicam.describe()}

    @app.get("/api/v1/status")
    def status():
        ble = runtime.ble.snapshot()
        return {
            "sources": runtime.multicam.describe(),
            "active": runtime.multicam.active_id,
            "view_mode": runtime.view_mode,
            "paused": runtime.paused,
            "ble": {
                "connected": ble.connected,
                "device_name": ble.device_name,
                "address": ble.address,
                "negotiated_url": ble.negotiated_url,
                "devices": ble.devices,
            },
            "usb": runtime.rig.get_usb_state(),
            "serial_ports": runtime.rig.list_serial_ports(),
            "result": runtime.latest_result(),
        }

    @app.get("/api/v1/analytics")
    def analytics(source_id: str | None = None):
        return runtime.latest_result(source_id)

    @app.get("/api/v1/cameras/usb")
    def cameras_usb():
        return {"cameras": runtime.list_usb_inventory()}

    @app.post("/api/v1/cameras/usb/open-all")
    def cameras_usb_open_all():
        return {"source_ids": runtime.open_all_usb()}

    @app.post("/api/v1/cameras/pc")
    def cameras_pc():
        try:
            sid = runtime.open_pc_camera()
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"source_id": sid}

    @app.get("/api/v1/cameras/wifi")
    def cameras_wifi():
        return {"endpoints": runtime.scan_wifi()}

    @app.get("/api/v1/cameras/bluetooth")
    def cameras_bluetooth():
        ble = runtime.ble.snapshot()
        return {
            "connected": ble.connected,
            "device_name": ble.device_name,
            "address": ble.address,
            "negotiated_url": ble.negotiated_url,
            "devices": ble.devices,
        }

    @app.post("/api/v1/source")
    def source(body: SourceIn):
        try:
            sid = runtime.switch_source(body.backend, body.url)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"source_id": sid}

    @app.post("/api/v1/source/select")
    def source_select(source_id: str = Query(...)):
        try:
            sid = runtime.select_source(source_id)
        except KeyError as exc:
            raise HTTPException(404, "unknown source") from exc
        return {"source_id": sid}

    @app.post("/api/v1/source/remove")
    def source_remove(source_id: str = Query(...)):
        runtime.multicam.remove_source(source_id)
        return {"ok": True}

    @app.post("/api/v1/view")
    def view(body: ViewIn):
        if body.mode not in {"active", "mosaic"}:
            raise HTTPException(400, "mode must be active or mosaic")
        runtime.view_mode = body.mode
        if body.source_id:
            try:
                runtime.select_source(body.source_id)
            except KeyError as exc:
                raise HTTPException(404, "unknown source") from exc
        return {"view_mode": runtime.view_mode, "active": runtime.multicam.active_id}

    @app.post("/api/v1/control")
    def control(body: ControlIn):
        if body.source_id:
            src = runtime.multicam.get(body.source_id)
            if src is not None:
                runtime.rig.attach(src)
        return runtime.rig.set(body.name, body.value)

    @app.post("/api/v1/ptz")
    def ptz(body: PtzIn):
        return runtime.rig.ptz(body.pan, body.tilt, body.zoom)

    @app.post("/api/v1/pause")
    def pause(paused: bool = Query(True)):
        runtime.paused = paused
        return {"paused": runtime.paused}

    @app.post("/api/v1/link/phone")
    def phone_link(body: PhoneLinkIn):
        state = runtime.ble.ingest_handshake(body.model_dump())
        sid = runtime.switch_source("http", body.stream_url)
        return {"ok": True, "source_id": sid, "device": state.device_name}

    @app.get("/api/v1/link/bluetooth")
    def bluetooth_status():
        ble = runtime.ble.snapshot()
        return {
            "connected": ble.connected,
            "device_name": ble.device_name,
            "address": ble.address,
            "negotiated_url": ble.negotiated_url,
            "transport": ble.transport,
            "last_telemetry": ble.last_telemetry,
            "devices": ble.devices,
        }

    @app.post("/api/v1/link/bluetooth/attach")
    def bluetooth_attach(address: str | None = None):
        url = runtime.ble.state.negotiated_url
        if address:
            gatt = runtime.ble.gatt_url_sync(address)
            if gatt:
                url = gatt
                runtime.ble.ingest_handshake({"stream_url": gatt, "address": address, "transport": "wifi_http"})
        if not url:
            raise HTTPException(400, "No phone stream URL from Bluetooth yet — open /phone on the device or scan again")
        sid = runtime.switch_source("http", url)
        return {"source_id": sid, "url": url}

    @app.get("/api/v1/stream.mjpg")
    def stream(source_id: str | None = None, mosaic_view: bool = Query(False, alias="mosaic")):
        def gen():
            import time

            while True:
                if mosaic_view:
                    runtime.view_mode = "mosaic"
                jpg = runtime.latest_jpeg(None if mosaic_view else source_id)
                if jpg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                time.sleep(1 / 30)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/ws/analytics")
    async def ws_analytics(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(runtime.latest_result())
                await asyncio.sleep(0.25)
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/ingress/{source_id}")
    async def ws_ingress(ws: WebSocket, source_id: str):
        await ws.accept()
        runtime.ensure_push(source_id, TransportKind.WIFI_HTTP)
        runtime.select_source(source_id)
        try:
            while True:
                message = await ws.receive()
                data = message.get("bytes")
                if data:
                    runtime.push_jpeg(source_id, data)
        except WebSocketDisconnect:
            return

    return app


def build(settings: AppSettings | None = None) -> tuple[FastAPI, Runtime]:
    settings = settings or AppSettings.load()
    runtime = Runtime(settings)
    runtime.start()
    return create_app(runtime), runtime
