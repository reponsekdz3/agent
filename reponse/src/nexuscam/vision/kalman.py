from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class ConstantVelocityKalman:
    """4-state CV filter in a plane: [x, y, vx, vy]."""

    def __init__(self, q: float = 8.0, r: float = 6.0) -> None:
        self.x = np.zeros((4, 1), dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 80.0
        self.q = q
        self.r = r
        self.initialized = False

    def predict(self, dt: float) -> NDArray[np.float64]:
        dt = max(dt, 1e-3)
        F = np.array(
            [
                [1, 0, dt, 0],
                [0, 1, 0, dt],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            dtype=np.float64,
        )
        q = self.q
        dt2, dt3, dt4 = dt * dt, dt**3, dt**4
        Q = q * np.array(
            [
                [dt4 / 4, 0, dt3 / 2, 0],
                [0, dt4 / 4, 0, dt3 / 2],
                [dt3 / 2, 0, dt2, 0],
                [0, dt3 / 2, 0, dt2],
            ],
            dtype=np.float64,
        )
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        return self.x.copy()

    def update(self, zx: float, zy: float) -> NDArray[np.float64]:
        z = np.array([[zx], [zy]], dtype=np.float64)
        if not self.initialized:
            self.x[:2] = z
            self.initialized = True
            return self.x.copy()
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64)
        R = np.eye(2) * self.r
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P
        return self.x.copy()

    @property
    def pos(self) -> tuple[float, float]:
        return float(self.x[0, 0]), float(self.x[1, 0])

    @property
    def vel(self) -> tuple[float, float]:
        return float(self.x[2, 0]), float(self.x[3, 0])

    @property
    def speed(self) -> float:
        vx, vy = self.vel
        return float(np.hypot(vx, vy))
