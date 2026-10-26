from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nexuscam.types import BoundingBox
from nexuscam.vision.kalman import ConstantVelocityKalman


def _hungarian(cost: np.ndarray) -> list[tuple[int, int]]:
    """Jonker-Volgenant-lite: square-pad then greedy dual-feasible assignment.

    For N<=64 tracks this is stable and dependency-free. SciPy is used when present.
    """
    if cost.size == 0:
        return []
    try:
        from scipy.optimize import linear_sum_assignment

        r, c = linear_sum_assignment(cost)
        return list(zip(r.tolist(), c.tolist()))
    except Exception:
        used_r, used_c = set(), set()
        pairs: list[tuple[int, int]] = []
        flat = [(cost[i, j], i, j) for i in range(cost.shape[0]) for j in range(cost.shape[1])]
        for _, i, j in sorted(flat):
            if i in used_r or j in used_c:
                continue
            used_r.add(i)
            used_c.add(j)
            pairs.append((i, j))
        return pairs


@dataclass
class Track:
    track_id: int
    box: BoundingBox
    label: str
    kf: ConstantVelocityKalman
    hits: int = 1
    age: int = 0
    miss: int = 0
    last_t_ns: int = 0
    speed_ema: float = 0.0
    extras: dict[str, float] = field(default_factory=dict)


class SortTracker:
    def __init__(self, iou_min: float = 0.3, max_age: int = 18, min_hits: int = 3) -> None:
        self.iou_min = iou_min
        self.max_age = max_age
        self.min_hits = min_hits
        self._tracks: list[Track] = []
        self._next_id = 1

    @property
    def tracks(self) -> list[Track]:
        return self._tracks

    def update(self, detections: list[tuple[BoundingBox, str]], t_ns: int) -> list[Track]:
        for tr in self._tracks:
            dt = (t_ns - tr.last_t_ns) / 1e9 if tr.last_t_ns else 1 / 30
            tr.kf.predict(dt)
            cx, cy = tr.kf.pos
            tr.box.x = cx - tr.box.w * 0.5
            tr.box.y = cy - tr.box.h * 0.5
            tr.age += 1
            tr.miss += 1

        if detections and self._tracks:
            cost = np.zeros((len(self._tracks), len(detections)), dtype=np.float64)
            for i, tr in enumerate(self._tracks):
                for j, (box, label) in enumerate(detections):
                    iou = tr.box.iou(box)
                    label_pen = 0.0 if (tr.label == label or tr.label == "unknown" or label == "unknown") else 0.25
                    cost[i, j] = (1.0 - iou) + label_pen
            assigned_t, assigned_d = set(), set()
            for i, j in _hungarian(cost):
                if i >= len(self._tracks) or j >= len(detections):
                    continue
                if 1.0 - cost[i, j] < self.iou_min and cost[i, j] > 1.0 - self.iou_min:
                    continue
                iou = self._tracks[i].box.iou(detections[j][0])
                if iou < self.iou_min:
                    continue
                self._commit(self._tracks[i], detections[j][0], detections[j][1], t_ns)
                assigned_t.add(i)
                assigned_d.add(j)
            unmatched_d = [j for j in range(len(detections)) if j not in assigned_d]
            unmatched_t = [i for i in range(len(self._tracks)) if i not in assigned_t]
        else:
            unmatched_d = list(range(len(detections)))
            unmatched_t = list(range(len(self._tracks)))

        for j in unmatched_d:
            box, label = detections[j]
            self._spawn(box, label, t_ns)

        alive: list[Track] = []
        for i, tr in enumerate(self._tracks):
            if i in unmatched_t and tr.miss > self.max_age:
                continue
            alive.append(tr)
        self._tracks = alive
        return [t for t in self._tracks if t.hits >= self.min_hits or t.miss == 0]

    def _spawn(self, box: BoundingBox, label: str, t_ns: int) -> None:
        kf = ConstantVelocityKalman()
        cx, cy = box.cxcy
        kf.update(cx, cy)
        self._tracks.append(
            Track(
                track_id=self._next_id,
                box=box,
                label=label,
                kf=kf,
                last_t_ns=t_ns,
            )
        )
        self._next_id += 1

    def _commit(self, tr: Track, box: BoundingBox, label: str, t_ns: int) -> None:
        cx, cy = box.cxcy
        tr.kf.update(cx, cy)
        tr.box = box
        if label != "unknown":
            tr.label = label
        tr.hits += 1
        tr.miss = 0
        tr.last_t_ns = t_ns
