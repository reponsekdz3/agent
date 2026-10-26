from __future__ import annotations

import cv2
import numpy as np

from aperture.capture.base import FrameSource
from aperture.types import CameraIdentity, Transport


class NetworkCamera(FrameSource):
    """Wi-Fi / LAN ingest: RTSP, HTTP MJPEG, or file-like OpenCV URLs."""

    def __init__(self, url: str, camera_id: str | None = None, name: str | None = None) -> None:
        self.url = url
        self._cap: cv2.VideoCapture | None = None
        kind = "rtsp" if url.lower().startswith("rtsp") else "http"
        cid = camera_id or f"wifi:{abs(hash(url)) % 10_000_000}"
        self.identity = CameraIdentity(
            camera_id=cid,
            name=name or f"Network camera ({kind})",
            transport=Transport.WIFI,
            endpoint=url,
            capabilities=("stream.start", "stream.stop", "ptz"),
            metadata={"protocol": kind},
        )

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.url)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open network stream: {self.url}")
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            return False, None
        ok, frame = self._cap.read()
        return bool(ok), frame if ok else None

    def apply_params(self, params: dict) -> None:
        return None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
