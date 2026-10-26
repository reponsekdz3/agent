from __future__ import annotations

import numpy as np

from nexuscam.settings import CalibrationCfg
from nexuscam.types import BoundingBox, Detection, PersonMeasurement
from nexuscam.vision.tracker import Track


def _pixel_ray_height(box: BoundingBox, face: BoundingBox | None, calib: CalibrationCfg) -> dict[str, float]:
    """Pinhole stature from vertical span, assuming feet on z=0 and small pitch."""
    fy = calib.fy
    face_px = face.h if face is not None else box.h * 0.13
    face_m = calib.reference_face_height_m
    # Distance from similar triangles: Z = fy * real / pixels
    z_face = fy * face_m / max(face_px, 1.0)
    stature = box.h * z_face / max(fy, 1e-6)  # wait that's wrong
    # Correct: image height h_px ≈ fy * H / Z  => H = h_px * Z / fy
    stature = box.h * z_face / fy
    face_h = face_px * z_face / fy
    shoulder = box.w * 0.42 * z_face / fy
    return {
        "z_m": z_face,
        "stature_m": float(np.clip(stature, 0.6, 2.3)),
        "face_height_m": float(np.clip(face_h, 0.12, 0.28)),
        "shoulder_width_m": float(np.clip(shoulder, 0.28, 0.62)),
        "face_px": face_px,
    }


def estimate_person(
    track: Track,
    detections: list[Detection],
    calib: CalibrationCfg,
) -> PersonMeasurement:
    face = None
    for d in detections:
        if d.label == "face" and _overlap(track.box, d.box) > 0.05:
            face = d.box
            break
    geom = _pixel_ray_height(track.box, face, calib)
    stature = geom["stature_m"]
    shoulder = geom["shoulder_width_m"]
    # Chest depth from shoulder via regression on CAESAR-like ratios
    chest = shoulder * 0.62
    # Ellipsoidal torso + cylindrical limbs volume, then density.
    torso_h = stature * 0.36
    volume = (4.0 / 3.0) * np.pi * (shoulder / 2) * (chest / 2) * (torso_h / 2)
    volume += np.pi * (0.05**2) * stature * 0.9  # limbs crude
    mass = float(volume * calib.assumed_body_density_kg_m3)
    # Face-height residual and bbox aspect feed uncertainty
    aspect = track.box.h / max(track.box.w, 1.0)
    conf = float(np.clip(0.35 + 0.2 * min(track.hits, 8) / 8 + (0.15 if face else 0) + (0.1 if 1.8 < aspect < 4.5 else 0), 0, 0.92))
    sigma = mass * (0.18 + (1.0 - conf) * 0.35)
    mass = float(np.clip(mass, 35.0, 160.0))
    note = (
        "Photogrammetric mass is a calibrated volume prior, not a scale. "
        "CI widens without ground-plane + face lock."
    )
    return PersonMeasurement(
        track_id=track.track_id,
        face_height_m=geom["face_height_m"],
        stature_m=stature,
        shoulder_width_m=shoulder,
        chest_depth_m=float(chest),
        mass_kg=mass,
        mass_ci95_kg=(max(30.0, mass - 1.96 * sigma), mass + 1.96 * sigma),
        confidence=conf,
        notes=note,
    )


def _overlap(a: BoundingBox, b: BoundingBox) -> float:
    return a.iou(b)
