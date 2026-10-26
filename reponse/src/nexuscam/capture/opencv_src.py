from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from nexuscam.capture.base import CaptureError, CaptureSource
from nexuscam.settings import CaptureCfg
from nexuscam.types import FramePacket, TransportKind


_PROP_MAP = {
    "brightness": cv2.CAP_PROP_BRIGHTNESS,
    "contrast": cv2.CAP_PROP_CONTRAST,
    "saturation": cv2.CAP_PROP_SATURATION,
    "hue": cv2.CAP_PROP_HUE,
    "gain": cv2.CAP_PROP_GAIN,
    "exposure": cv2.CAP_PROP_EXPOSURE,
    "focus": cv2.CAP_PROP_FOCUS,
    "zoom": cv2.CAP_PROP_ZOOM,
    "pan": cv2.CAP_PROP_PAN,
    "tilt": cv2.CAP_PROP_TILT,
    "autofocus": cv2.CAP_PROP_AUTOFOCUS,
    "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
    "fps": cv2.CAP_PROP_FPS,
    "width": cv2.CAP_PROP_FRAME_WIDTH,
    "height": cv2.CAP_PROP_FRAME_HEIGHT,
}


class OpenCvCapture(CaptureSource):
    """USB (UVC/MSMF/DSHOW) and URL (RTSP/HTTP MJPEG) ingest."""

    def __init__(
        self,
        target: int | str,
        cfg: CaptureCfg,
        transport: TransportKind,
        source_id: str,
    ) -> None:
        self._target = target
        self._cfg = cfg
        self._transport = transport
        self.source_id = source_id
        self._cap: cv2.VideoCapture | None = None
        self.friendly_name = source_id

    def start(self) -> None:
        if isinstance(self._target, int):
            cap = cv2.VideoCapture(self._target, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self._target, cv2.CAP_MSMF)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self._target)
        else:
            cap = cv2.VideoCapture(self._target, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, self._cfg.buffer_size)

        if not cap.isOpened():
            raise CaptureError(f"Cannot open capture target {self._target!r}")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self._cfg.fps)
        self._cap = cap

    def read(self, seq: int) -> FramePacket | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)
        return FramePacket(
            seq=seq,
            t_ns=time.time_ns(),
            bgr=frame,
            transport=self._transport,
            source_id=self.source_id,
        )

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def set_property(self, name: str, value: float) -> bool:
        if self._cap is None:
            return False
        prop = _PROP_MAP.get(name.lower())
        if prop is None:
            return False
        return bool(self._cap.set(prop, float(value)))

    def get_property(self, name: str) -> float | None:
        if self._cap is None:
            return None
        prop = _PROP_MAP.get(name.lower())
        if prop is None:
            return None
        val = float(self._cap.get(prop))
        return val

    def raw(self) -> Any:
        return self._cap
