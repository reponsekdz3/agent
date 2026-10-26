from __future__ import annotations

import math
import time

import cv2
import numpy as np

from aperture.capture.base import FrameSource
from aperture.types import CameraIdentity, Transport


class SyntheticRange(FrameSource):
    """Deterministic multi-object scene used as a hardware-in-the-loop substitute.

    Ground truth: person height 1.78 m, vehicle speeds 14.0 / 8.5 / 5.5 m/s.
    """

    WORLD_MPP = 0.04  # 4 cm per pixel on the painted ground strip

    def __init__(self, width: int = 1280, height: int = 720, fps: float = 30.0) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self._t0 = time.perf_counter()
        self._i = 0
        self.identity = CameraIdentity(
            camera_id="synthetic:range",
            name="Synthetic kinematics range",
            transport=Transport.SYNTHETIC,
            endpoint="memory://range",
            capabilities=("exposure", "gain", "zoom"),
            metadata={"ground_truth": True, "mpp": self.WORLD_MPP},
        )
        self._zoom = 1.0
        self._gain = 1.0
        rng = np.random.default_rng(7)
        self._noise = rng.integers(0, 18, (height, width, 3), dtype=np.uint8)

    def open(self) -> None:
        self._t0 = time.perf_counter()
        self._i = 0

    def apply_params(self, params: dict) -> None:
        if "zoom" in params:
            self._zoom = float(np.clip(params["zoom"], 1.0, 4.0))
        if "gain" in params:
            self._gain = float(np.clip(params["gain"], 0.4, 3.0))

    def close(self) -> None:
        return None

    def read(self) -> tuple[bool, np.ndarray | None]:
        t = time.perf_counter() - self._t0
        self._i += 1
        frame = self._render(t)
        return True, frame

    def _render(self, t: float) -> np.ndarray:
        h, w = self.height, self.width
        img = np.zeros((h, w, 3), dtype=np.uint8)
        horizon = int(h * 0.32)
        img[:horizon] = (42, 28, 18)
        img[horizon:] = (46, 52, 48)
        cv2.rectangle(img, (0, horizon), (w, h), (38, 44, 40), -1)
        # lane markings
        for y in range(horizon + 20, h, 28):
            offset = int((t * 180) % 80)
            for x in range(-40 + offset, w, 80):
                cv2.line(img, (x, y), (x + 36, y), (210, 210, 200), 2)
        # distant haze
        haze = np.linspace(0, 70, horizon, dtype=np.float32)
        img[:horizon, :, :] = np.clip(img[:horizon] + haze[:, None, None], 0, 255)

        vehicles = (
            ("car", 14.0, 0.62, (18, 90, 210), 92, 42),
            ("motorcycle", 8.5, 0.48, (30, 30, 30), 54, 36),
            ("bicycle", 5.5, 0.78, (20, 160, 90), 48, 32),
        )
        for name, speed, lane, color, bw, bh in vehicles:
            x = int((t * speed / self.WORLD_MPP + lane * 400) % (w + 200) - 80)
            y = int(horizon + 80 + lane * (h - horizon - 120))
            self._draw_vehicle(img, x, y, bw, bh, color, name)

        # walking person: 1.78 m tall at WORLD_MPP
        person_h = int(1.78 / self.WORLD_MPP)
        person_w = int(0.48 / self.WORLD_MPP)
        px = int(w * 0.22 + 40 * math.sin(t * 0.7))
        py = h - 40
        self._draw_person(img, px, py, person_w, person_h, t)

        img = cv2.addWeighted(img, self._gain, self._noise, 0.22, 0)
        if self._zoom > 1.01:
            zw, zh = int(w / self._zoom), int(h / self._zoom)
            x0, y0 = (w - zw) // 2, (h - zh) // 2
            crop = img[y0 : y0 + zh, x0 : x0 + zw]
            img = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
        # slight motion smear
        k = np.array([[0.05, 0.15, 0.05], [0.1, 0.3, 0.1], [0.05, 0.15, 0.05]], np.float32)
        img = cv2.filter2D(img, -1, k)
        return img

    @staticmethod
    def _draw_vehicle(img, x, y, bw, bh, color, name: str) -> None:
        cv2.rectangle(img, (x, y - bh), (x + bw, y), color, -1)
        cv2.rectangle(img, (x + 8, y - bh + 6), (x + bw - 8, y - bh // 2), (180, 220, 240), -1)
        cv2.circle(img, (x + 12, y), 7, (20, 20, 20), -1)
        cv2.circle(img, (x + bw - 12, y), 7, (20, 20, 20), -1)
        cv2.putText(img, name[:3].upper(), (x + 6, y - bh - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (240, 240, 240), 1)

    @staticmethod
    def _draw_person(img, cx, foot_y, bw, bh, t: float) -> None:
        x1, y1 = cx - bw // 2, foot_y - bh
        x2, y2 = cx + bw // 2, foot_y
        # torso
        cv2.rectangle(img, (x1 + 6, y1 + bh // 5), (x2 - 6, y1 + int(bh * 0.62)), (40, 55, 140), -1)
        # head / face
        head_c = (cx, y1 + bh // 8)
        cv2.circle(img, head_c, max(6, bw // 4), (210, 180, 160), -1)
        face_h = max(10, bh // 7)
        cv2.rectangle(
            img,
            (cx - bw // 6, head_c[1] - face_h // 2),
            (cx + bw // 6, head_c[1] + face_h // 2),
            (200, 160, 140),
            -1,
        )
        # legs
        phase = math.sin(t * 6.0)
        cv2.line(img, (cx - 4, y1 + int(bh * 0.62)), (cx - 10 + int(8 * phase), y2), (30, 30, 50), 5)
        cv2.line(img, (cx + 4, y1 + int(bh * 0.62)), (cx + 10 - int(8 * phase), y2), (30, 30, 50), 5)
