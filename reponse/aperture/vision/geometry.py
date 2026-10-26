from __future__ import annotations

import math

import numpy as np

from aperture.types import GroundPlane, Intrinsics


def default_intrinsics(width: int, height: int, focal_px: float | None = None) -> Intrinsics:
    f = float(focal_px if focal_px is not None else 0.85 * max(width, height))
    return Intrinsics(fx=f, fy=f, cx=width * 0.5, cy=height * 0.5, width=width, height=height)


def ground_from_height_tilt(intr: Intrinsics, height_m: float, tilt_deg: float) -> GroundPlane:
    """Pinhole camera looking down at tilt_deg from horizontal, optical axis in +Z cam.

    Camera frame: X right, Y down, Z forward. Ground is Y-up world mapped into camera.
    """
    tilt = math.radians(tilt_deg)
    # Normal of ground in camera coords (pointing up from road into camera-ish)
    ny = -math.cos(tilt)
    nz = -math.sin(tilt)
    n = np.array([0.0, ny, nz], dtype=np.float64)
    n /= np.linalg.norm(n) + 1e-9
    # Camera center is `height_m` above ground along world-up.
    world_up = np.array([0.0, -math.cos(tilt), -math.sin(tilt)])
    world_up /= np.linalg.norm(world_up) + 1e-9
    d = -float(n @ (world_up * height_m))
    return GroundPlane(nx=float(n[0]), ny=float(n[1]), nz=float(n[2]), d=d)


def pixel_ray(intr: Intrinsics, u: float, v: float) -> np.ndarray:
    x = (u - intr.cx) / intr.fx
    y = (v - intr.cy) / intr.fy
    d = np.array([x, y, 1.0], dtype=np.float64)
    return d / (np.linalg.norm(d) + 1e-9)


def intersect_ground(intr: Intrinsics, plane: GroundPlane, u: float, v: float) -> np.ndarray | None:
    ray = pixel_ray(intr, u, v)
    n = np.array([plane.nx, plane.ny, plane.nz], dtype=np.float64)
    denom = float(n @ ray)
    if abs(denom) < 1e-8:
        return None
    t = -plane.d / denom
    if t <= 0:
        return None
    return ray * t


def pixels_to_ground_xy(intr: Intrinsics, plane: GroundPlane, u: float, v: float) -> tuple[float, float] | None:
    p = intersect_ground(intr, plane, u, v)
    if p is None:
        return None
    # Project onto an on-plane basis: right = world X, forward along ground
    n = np.array([plane.nx, plane.ny, plane.nz], dtype=np.float64)
    right = np.array([1.0, 0.0, 0.0])
    right = right - n * float(right @ n)
    if np.linalg.norm(right) < 1e-6:
        right = np.array([0.0, 0.0, 1.0])
        right = right - n * float(right @ n)
    right /= np.linalg.norm(right) + 1e-9
    fwd = np.cross(n, right)
    fwd /= np.linalg.norm(fwd) + 1e-9
    return float(p @ right), float(p @ fwd)


def homography_pixels_to_meters(h: np.ndarray, u: float, v: float) -> tuple[float, float]:
    p = h @ np.array([u, v, 1.0], dtype=np.float64)
    if abs(p[2]) < 1e-9:
        return 0.0, 0.0
    return float(p[0] / p[2]), float(p[1] / p[2])


def estimate_homography(image_pts: np.ndarray, world_pts: np.ndarray) -> np.ndarray:
    if image_pts.shape[0] < 4:
        raise ValueError("Need >= 4 point correspondences")
    a = []
    for (u, v), (x, y) in zip(image_pts, world_pts):
        a.append([-u, -v, -1, 0, 0, 0, x * u, x * v, x])
        a.append([0, 0, 0, -u, -v, -1, y * u, y * v, y])
    a = np.asarray(a, dtype=np.float64)
    _, _, vt = np.linalg.svd(a)
    h = vt[-1].reshape(3, 3)
    return h / (h[2, 2] + 1e-12)
