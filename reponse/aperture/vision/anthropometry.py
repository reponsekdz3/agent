from __future__ import annotations

import math

import numpy as np

from aperture.settings import Settings
from aperture.types import Detection, GroundPlane, Intrinsics, ObjectClass, PersonMetrics
from aperture.vision.geometry import intersect_ground, pixels_to_ground_xy


class AnthropometryEngine:
    """Metric body reconstruction from a calibrated ground plane.

    Height: ray-plane intersection at the head and feet.
    Face height: forehead-to-chin in the same metric frame.
    Mass: stacked elliptical-frustum volume (NASA/anthropometric density),
    reported with an uncertainty that grows when the camera is uncalibrated.
    Camera-only mass is an estimate, not a scale reading.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.density = settings.person_density_kg_m3

    def measure(
        self,
        people: list[Detection],
        faces: list[Detection],
        intr: Intrinsics,
        plane: GroundPlane,
        mpp_override: float | None = None,
    ) -> list[PersonMetrics]:
        out: list[PersonMetrics] = []
        for person in people:
            if person.cls != ObjectClass.PERSON:
                continue
            face = _nearest_face(person, faces)
            height_m, conf_h, method = self._stature(person, intr, plane, mpp_override)
            face_h = self._face_height(face, person, height_m, mpp_override, plane, intr)
            shoulder = None
            torso = None
            if height_m:
                shoulder = 0.259 * height_m  # Pheasant/NASA mean shoulder/stature
                torso = 0.30 * height_m
                if person.width and person.height:
                    mpp = (height_m / person.height) if person.height else None
                    if mpp:
                        shoulder = 0.55 * person.width * mpp + 0.45 * shoulder
            mass, mass_u = self._mass(person, height_m, shoulder, mpp_override, plane)
            out.append(
                PersonMetrics(
                    track_id=person.track_id,
                    height_m=_r(height_m, 3),
                    face_height_m=_r(face_h, 4),
                    shoulder_width_m=_r(shoulder, 3),
                    torso_length_m=_r(torso, 3),
                    estimated_mass_kg=_r(mass, 1),
                    mass_uncertainty_kg=_r(mass_u, 1),
                    method=method,
                    confidence=float(np.clip(conf_h, 0.05, 0.95)),
                )
            )
        return out

    def _stature(
        self,
        person: Detection,
        intr: Intrinsics,
        plane: GroundPlane,
        mpp: float | None,
    ) -> tuple[float | None, float, str]:
        head = intersect_ground(intr, plane, person.cx, person.y1)
        feet = intersect_ground(intr, plane, person.cx, person.y2)
        if head is not None and feet is not None:
            # Vertical distance along plane normal
            n = np.array([plane.nx, plane.ny, plane.nz])
            # Head is not on the ground: intersect the head ray with a plane parallel
            # to ground through the camera origin offset is already in intersect_ground
            # for the foot. For the head, use similar-triangles with camera height.
            foot_xy = pixels_to_ground_xy(intr, plane, person.cx, person.y2)
            head_xy = pixels_to_ground_xy(intr, plane, person.cx, person.y1)
            if foot_xy and head_xy:
                # Range to feet
                z_f = float(np.linalg.norm(feet))
                z_h = float(np.linalg.norm(head))
                # Angular stature
                a_f = (person.y2 - intr.cy) / intr.fy
                a_h = (person.y1 - intr.cy) / intr.fy
                # Camera height along -n
                cam_h = abs(plane.d)
                if cam_h > 0.3:
                    stature = cam_h * (1.0 - (a_h / (a_f + 1e-6)))
                    # mix with pixel-span if mpp known
                    if mpp:
                        stature = 0.65 * stature + 0.35 * (person.height * mpp)
                    stature = float(np.clip(stature, 0.7, 2.4))
                    return stature, 0.72, "ray-plane+camera-height"
        if mpp:
            return float(np.clip(person.height * mpp, 0.7, 2.4)), 0.55, "ground-mpp"
        # Weak prior
        return 1.70, 0.18, "population-prior"

    def _face_height(
        self,
        face: Detection | None,
        person: Detection,
        height_m: float | None,
        mpp: float | None,
        plane: GroundPlane,
        intr: Intrinsics,
    ) -> float | None:
        if face is None:
            if height_m:
                return 0.135 * height_m
            return None
        px = face.height
        if face.keypoints.get("forehead") and face.keypoints.get("chin"):
            fy = face.keypoints["forehead"][1]
            cy = face.keypoints["chin"][1]
            px = abs(cy - fy)
        if mpp:
            return float(px * mpp)
        if height_m and person.height > 1:
            return float(px * (height_m / person.height))
        return 0.22 if px > 1 else None

    def _mass(
        self,
        person: Detection,
        height_m: float | None,
        shoulder_m: float | None,
        mpp: float | None,
        plane: GroundPlane,
    ) -> tuple[float | None, float | None]:
        if not height_m:
            return None, None
        # Three elliptical frustums: head, torso, legs
        h = height_m
        sw = shoulder_m or 0.26 * h
        hip = 0.85 * sw
        thigh = 0.55 * sw
        vol_head = _ellipsoid_volume(0.11 * h, 0.08 * h, 0.10 * h)
        vol_torso = _frustum_volume(sw * 0.5, hip * 0.5, 0.30 * h)
        vol_legs = 2 * _frustum_volume(thigh * 0.5, 0.05, 0.48 * h)
        vol_arms = 2 * _frustum_volume(0.05, 0.03, 0.32 * h)
        volume = vol_head + vol_torso + vol_legs + vol_arms
        mass = volume * self.density
        # Uncertainty: 8% calibrated geometry, 22% prior
        rel = 0.22 if (plane.homography is None and mpp is None) else 0.10
        if person.score < 0.4:
            rel += 0.08
        mass = float(np.clip(mass, 35.0, 160.0))
        return mass, mass * rel


def _ellipsoid_volume(a: float, b: float, c: float) -> float:
    return 4.0 / 3.0 * math.pi * a * b * c


def _frustum_volume(r1: float, r2: float, h: float) -> float:
    return math.pi * h / 3.0 * (r1 * r1 + r1 * r2 + r2 * r2)


def _nearest_face(person: Detection, faces: list[Detection]) -> Detection | None:
    best = None
    best_d = 1e9
    for f in faces:
        if f.cls != ObjectClass.FACE:
            continue
        if f.cx < person.x1 - 10 or f.cx > person.x2 + 10:
            continue
        if f.cy < person.y1 - 20 or f.cy > person.y1 + person.height * 0.45:
            continue
        d = abs(f.cx - person.cx) + abs(f.cy - (person.y1 + person.height * 0.12))
        if d < best_d:
            best, best_d = f, d
    return best


def _r(v: float | None, n: int) -> float | None:
    if v is None:
        return None
    return round(float(v), n)
