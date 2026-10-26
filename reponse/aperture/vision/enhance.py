from __future__ import annotations

import cv2
import numpy as np


class RealtimeEnhancer:
    """Motion-aware live grade: temporal NR, CLAHE, dehaze, unsharp.

    Designed for 720p@30 on CPU. Keeps a one-frame EMA in Lab to avoid smear on
    high-gradient edges (vehicles).
    """

    def __init__(
        self,
        temporal: float = 0.35,
        clip_limit: float = 2.4,
        sharpen: float = 0.55,
        dehaze: float = 0.18,
    ) -> None:
        self.temporal = float(np.clip(temporal, 0.0, 0.85))
        self.clip_limit = clip_limit
        self.sharpen = sharpen
        self.dehaze = dehaze
        self._prev_l: np.ndarray | None = None
        self._clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))

    def reset(self) -> None:
        self._prev_l = None

    def __call__(self, bgr: np.ndarray) -> np.ndarray:
        if bgr is None or bgr.size == 0:
            return bgr
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        lf = l.astype(np.float32)
        if self._prev_l is not None and self.temporal > 0:
            delta = np.abs(lf - self._prev_l)
            w = self.temporal * np.clip(1.0 - delta / 28.0, 0.0, 1.0)
            lf = (1.0 - w) * lf + w * self._prev_l
        self._prev_l = lf
        l8 = np.clip(lf, 0, 255).astype(np.uint8)
        l8 = self._clahe.apply(l8)
        if self.dehaze > 0:
            l8 = self._dark_channel_lift(bgr, l8)
        if self.sharpen > 0:
            blur = cv2.GaussianBlur(l8, (0, 0), 1.15)
            l8 = cv2.addWeighted(l8, 1.0 + self.sharpen, blur, -self.sharpen, 0)
        out = cv2.merge((l8, a, b))
        graded = cv2.cvtColor(out, cv2.COLOR_LAB2BGR)
        return self._tone(graded)

    def _dark_channel_lift(self, bgr: np.ndarray, l8: np.ndarray) -> np.ndarray:
        minc = np.min(bgr, axis=2).astype(np.float32)
        dc = cv2.erode(minc, np.ones((5, 5), np.uint8))
        air = float(np.percentile(dc, 97))
        if air < 8:
            return l8
        t = 1.0 - self.dehaze * (dc / (air + 1e-6))
        t = np.clip(t, 0.35, 1.0)
        lifted = (l8.astype(np.float32) - air) / t + air
        return np.clip(lifted, 0, 255).astype(np.uint8)

    @staticmethod
    def _tone(bgr: np.ndarray) -> np.ndarray:
        x = bgr.astype(np.float32) / 255.0
        x = np.clip(x * 1.06, 0, 1)
        # mild S-curve
        x = 0.5 * (1.0 + np.tanh(2.1 * (x - 0.5)))
        return (x * 255.0).astype(np.uint8)
