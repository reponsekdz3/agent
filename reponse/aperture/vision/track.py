from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aperture.types import Detection, ObjectClass
from aperture.vision.detect import _iou


@dataclass
class Track:
    track_id: int
    cls: ObjectClass
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    hits: int = 1
    misses: int = 0
    keypoints: dict = field(default_factory=dict)
    # constant-velocity in pixel space
    vx: float = 0.0
    vy: float = 0.0


class ByteLikeTracker:
    def __init__(self, max_misses: int = 18, iou_thr: float = 0.28) -> None:
        self.max_misses = max_misses
        self.iou_thr = iou_thr
        self._next = 1
        self.tracks: dict[int, Track] = {}

    def update(self, detections: list[Detection], dt: float) -> list[Detection]:
        for tr in self.tracks.values():
            tr.x1 += tr.vx * dt
            tr.y1 += tr.vy * dt
            tr.x2 += tr.vx * dt
            tr.y2 += tr.vy * dt
        unmatched_d = list(detections)
        unmatched_t = list(self.tracks.keys())
        pairs: list[tuple[float, int, Detection]] = []
        for tid in unmatched_t:
            tr = self.tracks[tid]
            for det in unmatched_d:
                if det.cls != tr.cls and not _compat(tr.cls, det.cls):
                    continue
                iou = _iou(_as_det(tr), det)
                if iou >= self.iou_thr:
                    pairs.append((iou, tid, det))
        pairs.sort(reverse=True, key=lambda p: p[0])
        used_t: set[int] = set()
        used_d: set[int] = set()
        for iou, tid, det in pairs:
            di = id(det)
            if tid in used_t or di in used_d:
                continue
            used_t.add(tid)
            used_d.add(di)
            self._integrate(self.tracks[tid], det, dt)
        for det in unmatched_d:
            if id(det) in used_d:
                continue
            tid = self._next
            self._next += 1
            self.tracks[tid] = Track(
                track_id=tid,
                cls=det.cls,
                x1=det.x1,
                y1=det.y1,
                x2=det.x2,
                y2=det.y2,
                score=det.score,
                keypoints=dict(det.keypoints),
            )
        for tid in list(self.tracks):
            if tid not in used_t and self.tracks[tid].track_id not in {
                t.track_id for t in self.tracks.values() if t.hits == 1 and t.misses == 0
            }:
                if tid not in used_t:
                    self.tracks[tid].misses += 1
                    if self.tracks[tid].misses > self.max_misses:
                        del self.tracks[tid]
        out: list[Detection] = []
        for tr in self.tracks.values():
            if tr.misses > 0 and tr.hits < 2:
                continue
            out.append(
                Detection(
                    track_id=tr.track_id,
                    cls=tr.cls,
                    x1=tr.x1,
                    y1=tr.y1,
                    x2=tr.x2,
                    y2=tr.y2,
                    score=tr.score,
                    keypoints=dict(tr.keypoints),
                )
            )
        return out

    def _integrate(self, tr: Track, det: Detection, dt: float) -> None:
        cx0, cy0 = 0.5 * (tr.x1 + tr.x2), 0.5 * (tr.y1 + tr.y2)
        alpha = 0.65
        tr.x1 = alpha * det.x1 + (1 - alpha) * tr.x1
        tr.y1 = alpha * det.y1 + (1 - alpha) * tr.y1
        tr.x2 = alpha * det.x2 + (1 - alpha) * tr.x2
        tr.y2 = alpha * det.y2 + (1 - alpha) * tr.y2
        cx1, cy1 = 0.5 * (tr.x1 + tr.x2), 0.5 * (tr.y1 + tr.y2)
        if dt > 1e-4:
            tr.vx = 0.6 * tr.vx + 0.4 * (cx1 - cx0) / dt
            tr.vy = 0.6 * tr.vy + 0.4 * (cy1 - cy0) / dt
        tr.score = det.score
        if det.keypoints:
            tr.keypoints = det.keypoints
        tr.hits += 1
        tr.misses = 0


def _as_det(tr: Track) -> Detection:
    return Detection(tr.track_id, tr.cls, tr.x1, tr.y1, tr.x2, tr.y2, tr.score, tr.keypoints)


def _compat(a: ObjectClass, b: ObjectClass) -> bool:
    if a == b:
        return True
    return {a, b} <= {ObjectClass.PERSON, ObjectClass.FACE}
