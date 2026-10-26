from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import cv2

from nexuscam.bus.frame_bus import FrameBus
from nexuscam.capture.bluetooth_link import BluetoothControlPlane
from nexuscam.capture.multicam import MultiCameraManager
from nexuscam.capture.push_src import PushCapture
from nexuscam.capture.usb_enum import enumerate_usb_cameras
from nexuscam.capture.wifi_scan import discover_wifi_cameras
from nexuscam.control.rig import CameraRig
from nexuscam.enhance.pipeline import RealtimeEnhancer
from nexuscam.settings import AppSettings
from nexuscam.types import AnalysisResult, FramePacket, TransportKind
from nexuscam.vision.engine import VisionEngine
from nexuscam.vision.mosaic import mosaic
from nexuscam.vision.overlay import draw_analytics

log = logging.getLogger(__name__)


def _jsonable(result: AnalysisResult) -> dict:
    objects = []
    for o in result.objects:
        x1, y1, x2, y2 = o.box.xyxy
        objects.append(
            {
                "track_id": o.track_id,
                "label": o.label,
                "kind": o.kind,
                "score": o.score,
                "box": [x1, y1, x2, y2],
                "width_px": o.width_px,
                "height_px": o.height_px,
                "width_m": o.width_m,
                "height_m": o.height_m,
                "speed_mps": o.speed_mps,
                "speed_kph": o.speed_kph,
                "heading_deg": o.heading_deg,
                "world_xy_m": o.world_xy_m,
                "stature_m": o.stature_m,
                "face_height_m": o.face_height_m,
                "mass_kg": o.mass_kg,
                "mass_uncertainty_kg": o.mass_uncertainty_kg,
                "extras": o.extras,
                "lines": o.lines(),
            }
        )
    return {
        "seq": result.seq,
        "fps": result.fps,
        "enhance_ms": result.enhance_ms,
        "vision_ms": result.vision_ms,
        "source_id": result.source_id,
        "transport": result.transport.value,
        "counts": result.counts,
        "objects": objects,
        "people": [asdict(p) for p in result.people],
    }


class Runtime:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.bus = FrameBus(depth=8)
        self.ble = BluetoothControlPlane(settings.bluetooth)
        self.multicam = MultiCameraManager(settings, self.bus)
        self.rig = CameraRig(settings, None)
        self._lock = threading.Lock()
        self._jpeg_by_source: dict[str, bytes] = {}
        self._vis_by_source: dict[str, object] = {}
        self._result_by_source: dict[str, dict] = {}
        self._mosaic_jpeg = b""
        self._active_result: dict = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._engines: dict[str, VisionEngine] = {}
        self._enhancers: dict[str, RealtimeEnhancer] = {}
        self.paused = False
        self.view_mode = "active"  # active | mosaic
        self._executor: ThreadPoolExecutor | None = None

    def start(self) -> None:
        self.multicam.start()
        src = self.multicam.get(self.multicam.active_id) if self.multicam.active_id else None
        if src is not None:
            self.rig.attach(src)
        self.ble.start()
        self.bus.subscribe("vision")
        self._stop.clear()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="vis")
        vis = threading.Thread(target=self._vision_loop, name="vision", daemon=True)
        vis.start()
        self._threads = [vis]
        log.info("Runtime started sources=%s", self.multicam.list_ids())

    def stop(self) -> None:
        self._stop.set()
        self.bus.close()
        self.ble.stop()
        self.multicam.stop()
        if self._executor is not None:
            self._executor.shutdown(wait=False)

    def switch_source(self, backend: str, url: str | None = None) -> str:
        sid = self.multicam.switch_source(backend, url)
        src = self.multicam.get(sid)
        if src is not None:
            self.rig.attach(src)
            self.multicam.select(sid)
        self.view_mode = "active"
        return sid

    def select_source(self, source_id: str) -> str:
        sid = self.multicam.select(source_id)
        src = self.multicam.get(sid)
        if src is not None:
            self.rig.attach(src)
        self.view_mode = "active"
        return sid

    def open_all_usb(self) -> list[str]:
        ids = self.multicam.open_all_usb()
        if ids:
            self.select_source(ids[0])
        return ids

    def open_pc_camera(self) -> str:
        return self.switch_source("pc")

    def list_usb_inventory(self) -> list[dict]:
        cams = enumerate_usb_cameras(self.settings.capture.max_usb_index)
        return [
            {
                "index": c.index,
                "name": c.name,
                "backend": c.backend,
                "width": c.width,
                "height": c.height,
                "is_pc_camera": c.is_pc_camera,
                "source_id": c.source_id,
            }
            for c in cams
        ]

    def scan_wifi(self) -> list[dict]:
        hits = discover_wifi_cameras(ports=tuple(self.settings.phone.discovery_ports))
        return [{"host": h.host, "port": h.port, "url": h.url, "kind": h.kind} for h in hits]

    def ensure_push(self, source_id: str, transport: TransportKind = TransportKind.WIFI_HTTP) -> PushCapture:
        src = self.multicam.ensure_push(source_id, transport)
        self.rig.attach(src)
        return src

    def push_jpeg(self, source_id: str, data: bytes) -> None:
        src = self.ensure_push(source_id)
        src.push_jpeg(data)

    def latest_jpeg(self, source_id: str | None = None) -> bytes:
        with self._lock:
            if self.view_mode == "mosaic" and source_id is None:
                return self._mosaic_jpeg
            sid = source_id or self.multicam.active_id
            if sid and sid in self._jpeg_by_source:
                return self._jpeg_by_source[sid]
            if self._jpeg_by_source:
                return next(iter(self._jpeg_by_source.values()))
            return self._mosaic_jpeg

    def latest_result(self, source_id: str | None = None) -> dict:
        with self._lock:
            sid = source_id or self.multicam.active_id
            if sid and sid in self._result_by_source:
                return dict(self._result_by_source[sid])
            return dict(self._active_result)

    def _pipeline_for(self, source_id: str) -> tuple[RealtimeEnhancer, VisionEngine]:
        enh = self._enhancers.get(source_id)
        if enh is None:
            enh = RealtimeEnhancer(self.settings.enhance)
            self._enhancers[source_id] = enh
        eng = self._engines.get(source_id)
        if eng is None:
            eng = VisionEngine(self.settings)
            self._engines[source_id] = eng
        return enh, eng

    def _vision_loop(self) -> None:
        while not self._stop.is_set() and not self.bus.closed:
            if self.paused:
                time.sleep(0.03)
                continue
            pkt = self.bus.get("vision", timeout=0.5)
            if pkt is None:
                continue
            try:
                if self._executor is not None:
                    self._executor.submit(self._process_packet, pkt)
                else:
                    self._process_packet(pkt)
            except Exception:
                self._process_packet(pkt)

    def _process_packet(self, pkt: FramePacket) -> None:
        enh, engine = self._pipeline_for(pkt.source_id)
        t0 = time.perf_counter()
        enhanced = enh(pkt.bgr)
        enhance_ms = (time.perf_counter() - t0) * 1000.0
        work = FramePacket(
            seq=pkt.seq,
            t_ns=pkt.t_ns,
            bgr=enhanced,
            transport=pkt.transport,
            source_id=pkt.source_id,
            dropped_upstream=pkt.dropped_upstream,
        )
        result = engine.analyze(work, enhance_ms)
        vis = draw_analytics(enhanced, result)
        ok, buf = cv2.imencode(".jpg", vis, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            return
        jpeg = buf.tobytes()
        payload = _jsonable(result)
        with self._lock:
            self._jpeg_by_source[pkt.source_id] = jpeg
            self._vis_by_source[pkt.source_id] = vis
            self._result_by_source[pkt.source_id] = payload
            if pkt.source_id == self.multicam.active_id:
                self._active_result = payload
            labeled = {sid: frame for sid, frame in self._vis_by_source.items() if frame is not None}
            grid = mosaic(labeled)  # type: ignore[arg-type]
            ok2, buf2 = cv2.imencode(".jpg", grid, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
            if ok2:
                self._mosaic_jpeg = buf2.tobytes()
