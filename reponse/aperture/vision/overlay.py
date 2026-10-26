from __future__ import annotations

import cv2
import numpy as np

from aperture.types import Detection, FramePacket, KinematicState, ObjectClass, PersonMetrics

_COLORS = {
    ObjectClass.PERSON: (90, 200, 255),
    ObjectClass.FACE: (180, 220, 255),
    ObjectClass.CAR: (80, 160, 255),
    ObjectClass.MOTORCYCLE: (60, 80, 255),
    ObjectClass.BICYCLE: (80, 220, 120),
    ObjectClass.UNKNOWN: (200, 200, 200),
}


def annotate(bgr: np.ndarray, packet: FramePacket) -> np.ndarray:
    vis = bgr.copy()
    people = {p.track_id: p for p in packet.people}
    kin = {k.track_id: k for k in packet.kinematics}
    for det in packet.detections:
        color = _COLORS.get(det.cls, (200, 200, 200))
        p1 = (int(det.x1), int(det.y1))
        p2 = (int(det.x2), int(det.y2))
        cv2.rectangle(vis, p1, p2, color, 2)
        bits = [f"#{det.track_id}", det.cls.value]
        if det.track_id in kin:
            k = kin[det.track_id]
            bits.append(f"{k.speed_kph:0.1f} km/h")
        if det.track_id in people:
            m = people[det.track_id]
            if m.height_m:
                bits.append(f"H {m.height_m:0.2f}m")
            if m.face_height_m:
                bits.append(f"face {m.face_height_m*100:0.1f}cm")
            if m.estimated_mass_kg:
                bits.append(f"{m.estimated_mass_kg:0.0f}±{m.mass_uncertainty_kg or 0:0.0f}kg")
        label = " | ".join(bits)
        cv2.putText(vis, label, (p1[0], max(18, p1[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
        for name, (x, y, s) in det.keypoints.items():
            cv2.circle(vis, (int(x), int(y)), 3, (0, 255, 255), -1)
    hud = [
        f"{packet.camera_id}  f#{packet.frame_index}  {packet.width}x{packet.height}",
        f"enhance {packet.enhance_ms:0.1f}ms  infer {packet.infer_ms:0.1f}ms  tracks {len(packet.detections)}",
    ]
    y = 22
    for line in hud:
        cv2.putText(vis, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)
        y += 22
    return vis
