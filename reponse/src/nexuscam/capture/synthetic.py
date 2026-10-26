from __future__ import annotations

import math
import time

import cv2
import numpy as np

from nexuscam.capture.base import CaptureSource
from nexuscam.settings import CaptureCfg
from nexuscam.types import Bgr, FramePacket, TransportKind


class SyntheticWorldCapture(CaptureSource):
    """Deterministic scene with known kinematics for bringing-up the stack.

    Ground plane is z=0. Camera looks down the +Y world axis from (0, -8, 4).
    Vehicles travel +X at programmed speeds; a pedestrian walks at 1.4 m/s.
    """

    def __init__(self, cfg: CaptureCfg) -> None:
        self._cfg = cfg
        self.source_id = "demo:synthetic-range"
        self.friendly_name = "Synthetic kinematics range"
        self._transport = TransportKind.DEMO
        self._t0 = time.perf_counter()
        self._rng = np.random.default_rng(7)

    def start(self) -> None:
        self._t0 = time.perf_counter()

    def stop(self) -> None:
        return None

    def read(self, seq: int) -> FramePacket | None:
        t = time.perf_counter() - self._t0
        frame = self.render(t, self._cfg.width, self._cfg.height)
        return FramePacket(
            seq=seq,
            t_ns=time.time_ns(),
            bgr=frame,
            transport=TransportKind.DEMO,
            source_id=self.source_id,
        )

    def render(self, t: float, w: int, h: int) -> Bgr:
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = (28, 26, 24)
        self._draw_road(img)
        self._draw_vehicle(img, x_m=-18.0 + 16.7 * t, lane=0, color=(40, 90, 220), kind="car")
        self._draw_vehicle(img, x_m=12.0 + -11.1 * t, lane=1, color=(210, 210, 210), kind="motorcycle")
        self._draw_vehicle(img, x_m=-8.0 + 6.2 * t, lane=2, color=(40, 190, 90), kind="bicycle")
        self._draw_vehicle(img, x_m=-22.0 + 12.0 * t, lane=0, color=(30, 40, 50), kind="truck")
        self._draw_vehicle(img, x_m=6.0 + 9.5 * t, lane=1, color=(20, 80, 160), kind="bus")
        self._draw_person(img, x_m=-4.0 + 1.4 * t, y_m=3.4)
        self._draw_person(img, x_m=2.0 + 1.1 * t, y_m=4.1)
        self._draw_dog(img, x_m=-6.0 + 3.2 * t, y_m=14.5)
        self._draw_cat(img, x_m=4.0 + 0.6 * math.sin(t), y_m=12.8)
        self._draw_bird(img, x_m=-2.0 + 4.0 * t, y_m=8.0, z=2.4 + 0.4 * math.sin(t * 3))
        self._draw_horse(img, x_m=-10.0 + 5.5 * t, y_m=16.2)
        grain = self._rng.integers(0, 18, img.shape, dtype=np.uint8)
        cv2.add(img, grain, img)
        return img

    def _project(self, x: float, y: float, z: float, w: int, h: int) -> tuple[int, int]:
        cam = np.array([0.0, -8.0, 4.2])
        p = np.array([x, y, z]) - cam
        # look toward +Y
        u = p[0] / max(p[1], 0.35)
        v = -p[2] / max(p[1], 0.35)
        px = int(w * 0.5 + u * w * 0.42)
        py = int(h * 0.52 + v * h * 0.55)
        return px, py

    def _draw_road(self, img: Bgr) -> None:
        h, w = img.shape[:2]
        pts = [
            self._project(-40, 0, 0, w, h),
            self._project(40, 0, 0, w, h),
            self._project(40, 18, 0, w, h),
            self._project(-40, 18, 0, w, h),
        ]
        cv2.fillConvexPoly(img, np.array(pts, np.int32), (46, 46, 48))
        for k in range(-8, 12):
            a = self._project(k * 4.0, 9.0, 0.02, w, h)
            b = self._project(k * 4.0 + 1.6, 9.0, 0.02, w, h)
            cv2.line(img, a, b, (210, 210, 210), 2)

    def _draw_vehicle(self, img: Bgr, x_m: float, lane: int, color: tuple[int, int, int], kind: str) -> None:
        h, w = img.shape[:2]
        y_m = 2.2 + lane * 3.1
        dims = {
            "car": (4.4, 1.8, 1.5),
            "motorcycle": (2.1, 0.7, 1.3),
            "bicycle": (1.7, 0.5, 1.15),
            "truck": (7.2, 2.4, 3.0),
            "bus": (11.0, 2.5, 3.2),
        }[kind]
        L, Wd, Ht = dims
        corners = [
            (x_m, y_m - Wd / 2, 0),
            (x_m + L, y_m - Wd / 2, 0),
            (x_m + L, y_m + Wd / 2, 0),
            (x_m, y_m + Wd / 2, 0),
            (x_m, y_m - Wd / 2, Ht),
            (x_m + L, y_m - Wd / 2, Ht),
            (x_m + L, y_m + Wd / 2, Ht),
            (x_m, y_m + Wd / 2, Ht),
        ]
        proj = [self._project(*c, w, h) for c in corners]
        base = np.array(proj[:4], np.int32)
        top = np.array(proj[4:], np.int32)
        cv2.fillConvexPoly(img, base, tuple(int(c * 0.55) for c in color))
        cv2.fillConvexPoly(img, top, color)
        for i in range(4):
            cv2.line(img, proj[i], proj[i + 4], color, 1)

    def _draw_person(self, img: Bgr, x_m: float, y_m: float) -> None:
        h, w = img.shape[:2]
        head = self._project(x_m, y_m, 1.78, w, h)
        foot = self._project(x_m, y_m, 0.0, w, h)
        hip = self._project(x_m, y_m, 0.92, w, h)
        shoulder = self._project(x_m, y_m, 1.42, w, h)
        x1 = min(head[0], foot[0]) - 10
        x2 = max(head[0], foot[0]) + 10
        y1 = min(head[1], foot[1])
        y2 = max(head[1], foot[1])
        cv2.rectangle(img, (x1, y1), (x2, y2), (70, 90, 160), -1)
        cv2.circle(img, head, max(6, abs(head[1] - shoulder[1]) // 2), (200, 185, 140), -1)
        phase = time.perf_counter() * 6.0
        lx = int(8 * math.sin(phase))
        cv2.line(img, hip, (foot[0] + lx, foot[1]), (40, 40, 70), 3)
        cv2.line(img, hip, (foot[0] - lx, foot[1]), (40, 40, 70), 3)

    def _draw_dog(self, img: Bgr, x_m: float, y_m: float) -> None:
        h, w = img.shape[:2]
        a = self._project(x_m, y_m, 0.0, w, h)
        b = self._project(x_m + 1.2, y_m, 0.55, w, h)
        cv2.ellipse(img, ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2), (max(18, abs(b[0] - a[0]) // 2), 12), 0, 0, 360, (42, 82, 140), -1)
        cv2.circle(img, b, 10, (36, 70, 120), -1)

    def _draw_cat(self, img: Bgr, x_m: float, y_m: float) -> None:
        h, w = img.shape[:2]
        a = self._project(x_m, y_m, 0.0, w, h)
        b = self._project(x_m + 0.5, y_m, 0.32, w, h)
        cv2.ellipse(img, ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2), (14, 8), 0, 0, 360, (20, 90, 180), -1)
        cv2.circle(img, b, 7, (18, 80, 170), -1)

    def _draw_bird(self, img: Bgr, x_m: float, y_m: float, z: float) -> None:
        h, w = img.shape[:2]
        p = self._project(x_m, y_m, z, w, h)
        wing = self._project(x_m + 0.45, y_m, z + 0.08, w, h)
        cv2.circle(img, p, 7, (40, 180, 220), -1)
        cv2.line(img, p, wing, (30, 150, 200), 3)

    def _draw_horse(self, img: Bgr, x_m: float, y_m: float) -> None:
        h, w = img.shape[:2]
        a = self._project(x_m, y_m, 0.0, w, h)
        b = self._project(x_m + 2.2, y_m, 1.6, w, h)
        cv2.rectangle(img, (min(a[0], b[0]), min(a[1], b[1])), (max(a[0], b[0]), max(a[1], b[1])), (40, 90, 150), -1)
        head = self._project(x_m + 2.3, y_m, 1.7, w, h)
        cv2.circle(img, head, 9, (30, 70, 120), -1)
