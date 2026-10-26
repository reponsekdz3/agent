from __future__ import annotations

import time
from collections import Counter

from nexuscam.settings import AppSettings
from nexuscam.types import AnalysisResult, FramePacket, ObjectAnalytics
from nexuscam.vision.anthropometry import estimate_person
from nexuscam.vision.appearance import color_name, dominant_color_bgr
from nexuscam.vision.detect import SceneDetector
from nexuscam.vision.kinematics import apply_homography, homography_matrix, track_to_kinematic
from nexuscam.vision.taxonomy import kind_of
from nexuscam.vision.tracker import SortTracker


class VisionEngine:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.detector = SceneDetector(try_dnn=True)
        v = settings.vision
        self.tracker = SortTracker(iou_min=v.iou_match, max_age=v.max_track_age, min_hits=v.min_track_hits)
        self._ema_fps = 30.0
        self._last_t = time.perf_counter()

    def analyze(self, packet: FramePacket, enhance_ms: float) -> AnalysisResult:
        t0 = time.perf_counter()
        dets = self.detector.detect(packet.bgr)
        v = self.settings.vision
        min_score = getattr(v, "min_score", 0.28)
        dets = [d for d in dets if d.box.score >= min_score]
        if not v.detect_people:
            dets = [d for d in dets if d.kind != "person"]
        if not v.detect_vehicles:
            dets = [d for d in dets if d.kind != "vehicle"]
        if not v.detect_animals:
            dets = [d for d in dets if d.kind != "animal"]
        if not v.detect_objects:
            dets = [d for d in dets if d.kind != "object"]
        pairs = [(d.box, d.label) for d in dets]
        tracks = self.tracker.update(pairs, packet.t_ns)
        people = []
        kinematics = []
        objects: list[ObjectAnalytics] = []
        try:
            H = homography_matrix(self.settings.calibration)
        except Exception:
            H = None
        for tr in tracks:
            kin = track_to_kinematic(tr, self.settings.calibration, self.settings.vision.speed_smooth)
            kinematics.append(kin)
            person = None
            if kind_of(tr.label) == "person":
                person = estimate_person(tr, dets, self.settings.calibration)
                people.append(person)
            width_m, height_m = _metric_size(tr.box, H)
            bgr_c = dominant_color_bgr(packet.bgr, tr.box)
            dwell_s = tr.age / max(self._ema_fps, 1.0)
            objects.append(
                ObjectAnalytics(
                    track_id=tr.track_id,
                    label=tr.label,
                    kind=kind_of(tr.label),
                    score=float(tr.box.score),
                    box=tr.box,
                    width_px=tr.box.w,
                    height_px=tr.box.h,
                    area_px=tr.box.area,
                    aspect=tr.box.w / max(tr.box.h, 1.0),
                    world_xy_m=kin.world_xy_m,
                    width_m=width_m,
                    height_m=person.stature_m if person else height_m,
                    speed_mps=kin.speed_mps,
                    speed_kph=(kin.speed_mps * 3.6) if kin.speed_mps is not None else None,
                    heading_deg=(kin.heading_rad * 57.2958) if kin.heading_rad is not None else None,
                    face_height_m=person.face_height_m if person else None,
                    stature_m=person.stature_m if person else None,
                    mass_kg=person.mass_kg if person else None,
                    mass_uncertainty_kg=(
                        (person.mass_ci95_kg[1] - person.mass_kg)
                        if person and person.mass_ci95_kg and person.mass_kg
                        else None
                    ),
                    extras={
                        "hits": float(tr.hits),
                        "age": float(tr.age),
                        "color": color_name(bgr_c),
                        "dwell_s": dwell_s,
                    },
                )
            )
        now = time.perf_counter()
        inst_fps = 1.0 / max(now - self._last_t, 1e-3)
        self._last_t = now
        self._ema_fps = 0.15 * inst_fps + 0.85 * self._ema_fps
        counts = dict(Counter(o.kind for o in objects))
        counts.update(Counter(o.label for o in objects))
        return AnalysisResult(
            t_ns=packet.t_ns,
            seq=packet.seq,
            objects=objects,
            people=people,
            kinematics=kinematics,
            fps=self._ema_fps,
            enhance_ms=enhance_ms,
            vision_ms=(now - t0) * 1000.0,
            source_id=packet.source_id,
            transport=packet.transport,
            counts=counts,
        )


def _metric_size(box, H):
    if H is None:
        return None, None
    import math

    x1, y1, x2, y2 = box.xyxy
    left = apply_homography(x1, y2, H)
    right = apply_homography(x2, y2, H)
    top = apply_homography(0.5 * (x1 + x2), y1, H)
    bot = apply_homography(0.5 * (x1 + x2), y2, H)
    width_m = None
    height_m = None
    if left and right:
        width_m = math.hypot(right[0] - left[0], right[1] - left[1])
    if top and bot:
        height_m = math.hypot(top[0] - bot[0], top[1] - bot[1])
    return width_m, height_m
