from __future__ import annotations

import logging
import threading
import time
from typing import Any

from nexuscam.bus.frame_bus import FrameBus
from nexuscam.capture.base import CaptureError, CaptureSource
from nexuscam.capture.opencv_src import OpenCvCapture
from nexuscam.capture.push_src import PushCapture
from nexuscam.capture.registry import open_pc_camera, open_source, open_usb_device
from nexuscam.capture.usb_enum import enumerate_usb_cameras
from nexuscam.settings import AppSettings
from nexuscam.types import TransportKind

log = logging.getLogger(__name__)


class MultiCameraManager:
    """Concurrent USB / PC / Wi-Fi / push sources into one frame bus."""

    def __init__(self, settings: AppSettings, bus: FrameBus) -> None:
        self.settings = settings
        self.bus = bus
        self._sources: dict[str, CaptureSource] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.active_id: str | None = None

    def start(self) -> None:
        cfg = self.settings.capture
        opened: list[str] = []
        if cfg.auto_open_all_usb or cfg.include_pc_camera or cfg.backend in {"auto", "usb", "pc"}:
            opened.extend(self.open_all_usb())
        if cfg.backend in {"demo", "synthetic"} or (cfg.backend == "auto" and not opened):
            try:
                opened.append(self.add_source(open_source(self.settings, override="demo")))
            except Exception as exc:
                log.warning("Demo source failed: %s", exc)
        if cfg.rtsp_url:
            try:
                opened.append(self.switch_source("rtsp", cfg.rtsp_url))
            except Exception as exc:
                log.warning("Configured RTSP failed: %s", exc)
        if not opened:
            try:
                self.add_source(open_source(self.settings))
            except Exception as exc:
                log.warning("Primary source failed to open: %s", exc)

    def stop(self) -> None:
        self._stop.set()
        for sid in list(self.list_ids()):
            try:
                self.remove_source(sid)
            except Exception:
                log.exception("Error removing source %s", sid)

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._sources.keys())

    def describe(self) -> list[dict[str, Any]]:
        rows = []
        with self._lock:
            items = list(self._sources.items())
        for sid, src in items:
            transport = getattr(src, "_transport", None)
            if transport is None and hasattr(src, "identity"):
                transport = getattr(src.identity, "transport", None)
            if isinstance(src, OpenCvCapture):
                transport = src._transport
            elif isinstance(src, PushCapture):
                transport = src._transport
            else:
                transport = TransportKind.DEMO
            name = getattr(src, "friendly_name", sid)
            rows.append(
                {
                    "source_id": sid,
                    "name": name,
                    "transport": transport.value if hasattr(transport, "value") else str(transport),
                    "active": sid == self.active_id,
                    "kind": type(src).__name__,
                }
            )
        return rows

    def get(self, source_id: str) -> CaptureSource | None:
        with self._lock:
            return self._sources.get(source_id)

    def add_source(self, source: CaptureSource) -> str:
        sid = source.source_id
        if sid in self.list_ids():
            self.remove_source(sid)
        source.start()
        t = threading.Thread(target=self._reader_loop, args=(source,), name=f"cap-{sid}", daemon=True)
        with self._lock:
            self._sources[sid] = source
            self._threads[sid] = t
            if self.active_id is None:
                self.active_id = sid
        t.start()
        log.info("Added source %s", sid)
        return sid

    def remove_source(self, source_id: str) -> None:
        with self._lock:
            src = self._sources.pop(source_id, None)
            self._threads.pop(source_id, None)
            if self.active_id == source_id:
                self.active_id = next(iter(self._sources), None)
        if src is None:
            return
        try:
            src.stop()
        except Exception:
            log.exception("Stopping source failed: %s", source_id)
        log.info("Removed source %s", source_id)

    def select(self, source_id: str) -> str:
        with self._lock:
            if source_id not in self._sources:
                raise KeyError(source_id)
            self.active_id = source_id
            return source_id

    def switch_source(self, backend: str, url: str | None = None) -> str:
        if url:
            self.settings.capture.rtsp_url = url
        override = backend
        if url and "://" in url and backend in {"rtsp", "http", "wifi", "phone", "wifi_http", "wifi_rtsp"}:
            override = url
        new = open_source(self.settings, override=override)
        return self.add_source(new)

    def open_all_usb(self) -> list[str]:
        ids: list[str] = []
        cams = enumerate_usb_cameras(self.settings.capture.max_usb_index)
        if not cams:
            log.info("USB enumeration found 0 cameras")
            return ids
        for cam in cams:
            try:
                ids.append(self.add_source(open_usb_device(cam, self.settings)))
            except Exception as exc:
                log.warning("USB %s (%s) failed: %s", cam.index, cam.name, exc)
        if not ids:
            try:
                ids.append(self.add_source(open_pc_camera(self.settings)))
            except Exception as exc:
                log.info("PC camera fallback failed: %s", exc)
        return ids

    def ensure_push(self, source_id: str, transport: TransportKind = TransportKind.WIFI_HTTP) -> PushCapture:
        existing = self.get(source_id)
        if isinstance(existing, PushCapture):
            return existing
        src = PushCapture(source_id, transport)
        self.add_source(src)
        return src

    def _reader_loop(self, source: CaptureSource) -> None:
        while not self._stop.is_set() and source.source_id in self.list_ids():
            seq = self.bus.next_seq()
            try:
                pkt = source.read(seq)
            except CaptureError:
                log.exception("Capture read error for %s", source.source_id)
                time.sleep(0.05)
                continue
            except Exception:
                log.exception("Unexpected read error for %s", source.source_id)
                time.sleep(0.05)
                continue
            if pkt is None:
                time.sleep(0.008)
                continue
            try:
                self.bus.publish(pkt)
            except Exception:
                log.exception("Failed to publish packet from %s", source.source_id)
