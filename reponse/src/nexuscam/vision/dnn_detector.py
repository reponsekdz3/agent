from __future__ import annotations

import logging

import cv2
import numpy as np

from nexuscam.types import Bgr, BoundingBox, Detection
from nexuscam.vision.taxonomy import canonical_label, kind_of

log = logging.getLogger(__name__)


class OpenCvDNNDetector:
    """OpenCV DNN backend for Caffe SSD, ONNX, and TensorFlow graphs."""

    def __init__(
        self,
        model: str | None = None,
        config: str | None = None,
        labels: list[str] | None = None,
    ) -> None:
        self.labels = [canonical_label(x) for x in (labels or [])]
        self.net = None
        if not model:
            return
        try:
            self.net = cv2.dnn.readNet(model, config) if config else cv2.dnn.readNet(model)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        except Exception as exc:
            log.warning("DNN model not loaded (%s)", exc)

    def detect(self, bgr: Bgr, conf_thresh: float = 0.38) -> list[Detection]:
        if self.net is None:
            return []
        h, w = bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(bgr, (300, 300)), 0.007843, (300, 300), 127.5)
        self.net.setInput(blob)
        out = self.net.forward()
        dets: list[Detection] = []
        arr = np.squeeze(out)
        if arr.ndim == 3:
            arr = arr.reshape(-1, arr.shape[-1])
        if arr.ndim != 2 or arr.shape[1] < 6:
            return []
        for row in arr:
            if row.size >= 7:
                score = float(row[2])
                cls_id = int(row[1])
                nx1, ny1, nx2, ny2 = map(float, row[3:7])
            else:
                cls_id = int(row[0])
                score = float(row[1])
                nx1, ny1, nx2, ny2 = map(float, row[2:6])
            if score < conf_thresh:
                continue
            if 0.0 <= nx1 <= 1.5:
                x1, y1, x2, y2 = nx1 * w, ny1 * h, nx2 * w, ny2 * h
            else:
                x1, y1, x2, y2 = nx1, ny1, nx2, ny2
            x1, y1 = max(0.0, x1), max(0.0, y1)
            x2, y2 = min(float(w), x2), min(float(h), y2)
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            raw = self.labels[cls_id] if 0 <= cls_id < len(self.labels) else str(cls_id)
            label = canonical_label(raw)
            dets.append(
                Detection(
                    box=BoundingBox(x1, y1, x2 - x1, y2 - y1, score),
                    label=label,
                    kind=kind_of(label),
                )
            )
        return dets
