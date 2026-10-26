from __future__ import annotations

import math

import numpy as np

from nexuscam.settings import CalibrationCfg
from nexuscam.types import KinematicTrack
from nexuscam.vision.tracker import Track


def apply_homography(x: float, y: float, H: np.ndarray) -> tuple[float, float] | None:
    p = H @ np.array([x, y, 1.0], dtype=np.float64)
    if abs(p[2]) < 1e-8:
        return None
    return float(p[0] / p[2]), float(p[1] / p[2])


def homography_matrix(calib: CalibrationCfg) -> np.ndarray:
    return np.array(calib.homography, dtype=np.float64)


def track_to_kinematic(track: Track, calib: CalibrationCfg, speed_smooth: float) -> KinematicTrack:
    H = homography_matrix(calib)
    cx, cy = track.box.cxcy
    # Use contact point (bottom-center) for ground-plane objects
    gx, gy = cx, track.box.y + track.box.h
    world = apply_homography(gx, gy, H)
    dt = 1.0 / 30.0
    if track.last_t_ns:
        pass
    vx_px, vy_px = track.kf.vel
    # Finite world velocity via homography of a forward point
    speed = None
    heading = None
    if world is not None:
        ahead = apply_homography(gx + vx_px * dt, gy + vy_px * dt, H)
        if ahead is not None:
            dx, dy = ahead[0] - world[0], ahead[1] - world[1]
            inst = math.hypot(dx, dy) / dt
            track.speed_ema = speed_smooth * inst + (1.0 - speed_smooth) * (track.speed_ema or inst)
            speed = track.speed_ema
            heading = math.atan2(dy, dx)
    return KinematicTrack(
        track_id=track.track_id,
        label=track.label,
        box=track.box,
        world_xy_m=world,
        speed_mps=speed,
        heading_rad=heading,
        hits=track.hits,
        age=track.age,
        extras={
            "px_speed": float(track.kf.speed),
            "kph": (speed * 3.6) if speed is not None else 0.0,
        },
    )


def solve_ground_homography(
    image_pts: list[tuple[float, float]],
    world_pts: list[tuple[float, float]],
) -> np.ndarray:
    """DLT homography from 4+ correspondences (image pixels -> meters on ground)."""
    if len(image_pts) < 4:
        raise ValueError("Need 4 point pairs")
    rows = []
    for (u, v), (x, y) in zip(image_pts, world_pts):
        rows.append([u, v, 1, 0, 0, 0, -x * u, -x * v, -x])
        rows.append([0, 0, 0, u, v, 1, -y * u, -y * v, -y])
    A = np.array(rows, dtype=np.float64)
    _, _, vt = np.linalg.svd(A)
    h = vt[-1]
    H = h.reshape(3, 3)
    return H / H[2, 2]
