from __future__ import annotations

import logging
from typing import Iterable

from aperture.capture.base import FrameSource
from aperture.capture.bluetooth import PhoneBridge
from aperture.capture.network import NetworkCamera
from aperture.capture.synthetic import SyntheticRange
from aperture.capture.usb import UsbCamera
from aperture.settings import Settings
from aperture.types import CameraIdentity

log = logging.getLogger("aperture.capture")


class CaptureManager:
    def __init__(self) -> None:
        self._sources: dict[str, FrameSource] = {}

    def add(self, source: FrameSource, open_now: bool = True) -> CameraIdentity:
        if open_now:
            try:
                source.open()
            except Exception as exc:
                log.warning("Failed to open %s: %s", source.identity.camera_id, exc)
                raise
        self._sources[source.identity.camera_id] = source
        return source.identity

    def get(self, camera_id: str) -> FrameSource | None:
        return self._sources.get(camera_id)

    def list(self) -> list[CameraIdentity]:
        return [s.identity for s in self._sources.values()]

    def read(self, camera_id: str):
        src = self._sources[camera_id]
        return src.read()

    def apply(self, camera_id: str, params: dict) -> None:
        src = self._sources.get(camera_id)
        if src:
            src.apply_params(params)

    def close_all(self) -> None:
        for src in self._sources.values():
            src.close()
        self._sources.clear()

    def bootstrap(self, settings: Settings, bridges: Iterable[PhoneBridge] = ()) -> list[CameraIdentity]:
        opened: list[CameraIdentity] = []
        if settings.synthetic:
            opened.append(self.add(SyntheticRange(fps=settings.target_fps)))
        if settings.rtsp_url:
            opened.append(self.add(NetworkCamera(settings.rtsp_url, name="RTSP camera")))
        if settings.mjpeg_url:
            opened.append(self.add(NetworkCamera(settings.mjpeg_url, name="MJPEG camera")))
        try:
            opened.append(self.add(UsbCamera(index=settings.usb_index, fps=settings.target_fps)))
        except Exception as exc:
            log.info("USB camera unavailable: %s", exc)
        for bridge in bridges:
            if bridge.stream_url and bridge.identity:
                try:
                    cam = NetworkCamera(
                        bridge.stream_url,
                        camera_id=bridge.identity.camera_id,
                        name=bridge.identity.name,
                    )
                    cam.identity = bridge.identity
                    opened.append(self.add(cam))
                except Exception as exc:
                    log.warning("Phone stream %s failed: %s", bridge.address, exc)
        if not opened:
            opened.append(self.add(SyntheticRange(fps=settings.target_fps)))
        return opened
