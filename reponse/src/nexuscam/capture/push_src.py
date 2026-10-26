from __future__ import annotations

import time
from threading import Lock

import cv2
import numpy as np

from nexuscam.capture.base import CaptureSource
from nexuscam.types import FramePacket, TransportKind


class PushCapture(CaptureSource):
    """Frames pushed from a phone/browser over WebSocket or HTTP (Wi-Fi / USB tether)."""

    def __init__(self, source_id: str, transport: TransportKind = TransportKind.WIFI_HTTP) -> None:
        self.source_id = source_id
        self._transport = transport
        self._lock = Lock()
        self._bgr: np.ndarray | None = None
        self._t_ns = 0

    def start(self) -> None:
        return None

    def stop(self) -> None:
        with self._lock:
            self._bgr = None

    def push_jpeg(self, data: bytes) -> None:
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return
        self.push_bgr(frame)

    def push_bgr(self, frame: np.ndarray) -> None:
        with self._lock:
            self._bgr = frame
            self._t_ns = time.time_ns()

    def read(self, seq: int) -> FramePacket | None:
        with self._lock:
            if self._bgr is None:
                return None
            frame = self._bgr
            t_ns = self._t_ns
        return FramePacket(
            seq=seq,
            t_ns=t_ns,
            bgr=frame,
            transport=self._transport,
            source_id=self.source_id,
        )
