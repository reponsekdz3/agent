from __future__ import annotations

import cv2
import numpy as np

from nexuscam.settings import EnhanceCfg
from nexuscam.types import Bgr


def _gray_world_awb(bgr: Bgr) -> Bgr:
    avg = bgr.reshape(-1, 3).mean(axis=0)
    avg = np.maximum(avg, 1.0)
    scale = avg.mean() / avg
    out = np.clip(bgr.astype(np.float32) * scale, 0, 255).astype(np.uint8)
    return out


class RealtimeEnhancer:
    """Motion-aware temporal fusion + local contrast + mild super-resolve sharpening.

    Designed for 720p30 on CPU. Temporal EMA is gated by Laplacian motion energy
    so headlights and wheels do not smear.
    """

    def __init__(self, cfg: EnhanceCfg) -> None:
        self.cfg = cfg
        self._prev: np.ndarray | None = None
        self._clahe = cv2.createCLAHE(
            clipLimit=cfg.clahe_clip, tileGridSize=(cfg.clahe_grid, cfg.clahe_grid)
        )

    def reset(self) -> None:
        self._prev = None

    def __call__(self, bgr: Bgr) -> Bgr:
        if not self.cfg.enabled:
            return bgr
        work = bgr
        if self.cfg.auto_white_balance:
            work = _gray_world_awb(work)

        if self.cfg.denoise_h > 0:
            work = cv2.fastNlMeansDenoisingColored(
                work, None, self.cfg.denoise_h, self.cfg.denoise_h, 5, 11
            )

        lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = self._clahe.apply(l)
        work = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

        blur = cv2.GaussianBlur(work, (0, 0), self.cfg.unsharp_radius)
        work = cv2.addWeighted(work, 1.0 + self.cfg.unsharp_amount, blur, -self.cfg.unsharp_amount, 0)

        if abs(self.cfg.gamma - 1.0) > 1e-3:
            inv = 1.0 / max(self.cfg.gamma, 0.05)
            table = np.array([((i / 255.0) ** inv) * 255 for i in range(256)]).astype(np.uint8)
            work = cv2.LUT(work, table)

        work = self._temporal(work)
        return work

    def _temporal(self, frame: Bgr) -> Bgr:
        alpha = float(np.clip(self.cfg.temporal_alpha, 0.0, 0.95))
        f32 = frame.astype(np.float32)
        if self._prev is None or self._prev.shape != f32.shape:
            self._prev = f32
            return frame
        diff = cv2.absdiff(f32, self._prev)
        energy = diff.mean(axis=2)
        gate = np.clip(1.0 - energy / 28.0, 0.15, 1.0)[..., None]
        fused = self._prev * (1.0 - alpha * gate) + f32 * (alpha * gate + (1.0 - alpha))
        # rewrite: high motion -> trust current frame; low motion -> blend
        motion = np.clip(energy / 40.0, 0.0, 1.0)[..., None]
        fused = f32 * (alpha * 0.25 + motion) + self._prev * (1.0 - (alpha * 0.25 + motion))
        fused = np.clip(fused, 0, 255)
        self._prev = fused
        return fused.astype(np.uint8)
