from __future__ import annotations

import math

import numpy as np

from aperture.types import Detection, GroundPlane, Intrinsics, KinematicState, ObjectClass
from aperture.vision.geometry import homography_pixels_to_meters, pixels_to_ground_xy


class ConstantVelocityKalman:
    """2D CV Kalman in world metres: state [x, y, vx, vy]."""

    def __init__(self, q_pos: float = 0.08, q_vel: float = 1.6, r_pos: float = 0.35) -> None:
        self.q_pos = q_pos
        self.q_vel = q_vel
        self.r_pos = r_pos
        self.x = np.zeros(4)
        self.P = np.eye(4) * 12.0
        self.ready = False

    def predict(self, dt: float) -> None:
        f = np.array(
            [
                [1, 0, dt, 0],
                [0, 1, 0, dt],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            dtype=np.float64,
        )
        q = np.diag([self.q_pos, self.q_pos, self.q_vel, self.q_vel])
        self.x = f @ self.x
        self.P = f @ self.P @ f.T + q

    def update(self, zx: float, zy: float) -> None:
        h = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64)
        r = np.eye(2) * self.r_pos
        z = np.array([zx, zy], dtype=np.float64)
        y = z - h @ self.x
        s = h @ self.P @ h.T + r
        k = self.P @ h.T @ np.linalg.inv(s)
        self.x = self.x + k @ y
        self.P = (np.eye(4) - k @ h) @ self.P
        self.ready = True


_PLAUSIBLE = {
    ObjectClass.CAR: (0.0, 70.0),
    ObjectClass.MOTORCYCLE: (0.0, 55.0),
    ObjectClass.BICYCLE: (0.0, 25.0),
    ObjectClass.PERSON: (0.0, 12.0),
}


class SpeedEngine:
    def __init__(self) -> None:
        self._filters: dict[int, ConstantVelocityKalman] = {}

    def update(
        self,
        dets: list[Detection],
        dt: float,
        intr: Intrinsics,
        plane: GroundPlane,
        mpp: float | None,
    ) -> list[KinematicState]:
        live: set[int] = set()
        out: list[KinematicState] = []
        for det in dets:
            if det.cls not in (ObjectClass.CAR, ObjectClass.MOTORCYCLE, ObjectClass.BICYCLE, ObjectClass.PERSON):
                continue
            if det.track_id < 0:
                continue
            xy = self._world_xy(det, intr, plane, mpp)
            if xy is None:
                continue
            live.add(det.track_id)
            kf = self._filters.get(det.track_id)
            if kf is None:
                kf = ConstantVelocityKalman()
                kf.x[:2] = xy
                self._filters[det.track_id] = kf
            kf.predict(max(dt, 1e-3))
            kf.update(*xy)
            vx, vy = float(kf.x[2]), float(kf.x[3])
            speed = math.hypot(vx, vy)
            lo, hi = _PLAUSIBLE.get(det.cls, (0.0, 80.0))
            if speed > hi:
                # reject physically impossible spikes, keep previous velocity
                speed = hi
                scale = hi / (math.hypot(vx, vy) + 1e-9)
                vx, vy = vx * scale, vy * scale
                kf.x[2], kf.x[3] = vx, vy
            heading = math.degrees(math.atan2(vy, vx)) if speed > 0.15 else 0.0
            conf = float(np.clip(0.35 + 0.08 * det.score * 10, 0.2, 0.9))
            if mpp is None and plane.homography is None:
                conf *= 0.65
            out.append(
                KinematicState(
                    track_id=det.track_id,
                    cls=det.cls,
                    x_m=float(kf.x[0]),
                    y_m=float(kf.x[1]),
                    vx_mps=vx,
                    vy_mps=vy,
                    speed_mps=speed,
                    speed_kph=speed * 3.6,
                    heading_deg=heading,
                    confidence=conf,
                )
            )
        for tid in list(self._filters):
            if tid not in live:
                del self._filters[tid]
        return out

    @staticmethod
    def _world_xy(
        det: Detection, intr: Intrinsics, plane: GroundPlane, mpp: float | None
    ) -> tuple[float, float] | None:
        u, v = det.ground_point
        if plane.homography is not None:
            h = np.asarray(plane.homography, dtype=np.float64)
            return homography_pixels_to_meters(h, u, v)
        xy = pixels_to_ground_xy(intr, plane, u, v)
        if xy is not None:
            return xy
        if mpp:
            return u * mpp, v * mpp
        return None
