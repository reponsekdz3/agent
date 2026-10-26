from __future__ import annotations

import logging

import cv2
import numpy as np

from aperture.capture.base import FrameSource
from aperture.types import CameraIdentity, Transport

log = logging.getLogger("aperture.capture.usb")


class UsbCamera(FrameSource):
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, fps: float = 30.0) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap: cv2.VideoCapture | None = None
        self.identity = CameraIdentity(
            camera_id=f"usb:{index}",
            name=f"USB camera {index}",
            transport=Transport.USB,
            endpoint=f"dshow://{index}",
            capabilities=("exposure", "gain", "focus", "zoom", "fps", "resolution"),
        )

    def open(self) -> None:
        backends = []
        if hasattr(cv2, "CAP_DSHOW"):
            backends.append(cv2.CAP_DSHOW)
        if hasattr(cv2, "CAP_MSMF"):
            backends.append(cv2.CAP_MSMF)
        backends.append(cv2.CAP_ANY)
        last_err = None
        for backend in backends:
            cap = cv2.VideoCapture(self.index, backend)
            if cap.isOpened():
                self._cap = cap
                break
            last_err = backend
            cap.release()
        if self._cap is None:
            raise RuntimeError(f"USB camera {self.index} could not be opened (last backend={last_err})")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            return False, None
        ok, frame = self._cap.read()
        return bool(ok), frame if ok else None

    def apply_params(self, params: dict) -> None:
        if self._cap is None:
            return
        mapping = {
            "exposure": cv2.CAP_PROP_EXPOSURE,
            "gain": cv2.CAP_PROP_GAIN,
            "focus": cv2.CAP_PROP_FOCUS,
            "zoom": cv2.CAP_PROP_ZOOM,
            "fps": cv2.CAP_PROP_FPS,
            "brightness": cv2.CAP_PROP_BRIGHTNESS,
            "contrast": cv2.CAP_PROP_CONTRAST,
            "saturation": cv2.CAP_PROP_SATURATION,
            "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
        }
        for key, prop in mapping.items():
            if key in params:
                self._cap.set(prop, float(params[key]))
        if "width" in params:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(params["width"]))
        if "height" in params:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(params["height"]))

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def backend_handle(self):
        return self._cap
