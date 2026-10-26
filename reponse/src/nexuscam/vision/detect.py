from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from nexuscam.types import Bgr, BoundingBox, Detection
from nexuscam.vision.dnn_detector import OpenCvDNNDetector
from nexuscam.vision.taxonomy import canonical_label, kind_of
from nexuscam.vision.weights import DISPLAY, KIND_OF, SSD_NAMES, ensure_ssd


class SceneDetector:
    """People, vehicles, animals, and generic objects.

    MobileNet-SSD when weights exist; HOG / Haar / motion-saliency always run so
    USB, Wi-Fi, and the synthetic range still produce labeled green boxes.
    """

    def __init__(self, try_dnn: bool = True) -> None:
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self._face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self._profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
        cat_path = cv2.data.haarcascades + "haarcascade_frontalcatface.xml"
        self._cat = cv2.CascadeClassifier(cat_path)
        self._bg = cv2.createBackgroundSubtractorMOG2(history=240, varThreshold=10, detectShadows=True)
        self._dnn = _try_load_ssd() if try_dnn else None
        self._pluggable: OpenCvDNNDetector | None = None
        try:
            from nexuscam.settings import AppSettings

            settings = AppSettings.load()
            if settings.vision.dnn_model:
                self._pluggable = OpenCvDNNDetector(
                    settings.vision.dnn_model,
                    settings.vision.dnn_config or None,
                    settings.vision.dnn_labels,
                )
        except Exception:
            self._pluggable = None

    def detect(self, bgr: Bgr) -> list[Detection]:
        out: list[Detection] = []
        if self._dnn is not None:
            out.extend(self._dnn_detect(bgr))
        if self._pluggable is not None:
            try:
                out.extend(self._pluggable.detect(bgr))
            except Exception:
                pass
        out.extend(self._hog_people(bgr))
        out.extend(self._faces(bgr))
        out.extend(self._cats(bgr))
        out.extend(self._motion_and_salient(bgr))
        return _nms(out, 0.45)

    def _dnn_detect(self, bgr: Bgr) -> list[Detection]:
        net, size, mean = self._dnn  # type: ignore[misc]
        h, w = bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(bgr, 0.007843, size, mean, False, False)
        net.setInput(blob)
        pred = net.forward()
        dets: list[Detection] = []
        for i in range(pred.shape[2]):
            conf = float(pred[0, 0, i, 2])
            if conf < 0.35:
                continue
            cls_id = int(pred[0, 0, i, 1])
            raw = SSD_NAMES.get(cls_id, "object")
            label = canonical_label(DISPLAY.get(raw, raw))
            kind = KIND_OF.get(raw, kind_of(label))
            x1, y1, x2, y2 = pred[0, 0, i, 3:7] * np.array([w, h, w, h])
            x1, y1 = max(0.0, float(x1)), max(0.0, float(y1))
            dets.append(
                Detection(
                    box=BoundingBox(x1, y1, float(max(2, x2 - x1)), float(max(2, y2 - y1)), conf),
                    label=label,
                    kind=kind,
                )
            )
        return dets

    def _hog_people(self, bgr: Bgr) -> list[Detection]:
        rects, weights = self._hog.detectMultiScale(bgr, winStride=(8, 8), padding=(8, 8), scale=1.05)
        dets: list[Detection] = []
        wts = weights.reshape(-1) if len(weights) else []
        for (x, y, w, h), s in zip(rects, wts if len(wts) else [0.6] * len(rects)):
            dets.append(
                Detection(
                    box=BoundingBox(float(x), float(y), float(w), float(h), float(np.clip(s / 2.5, 0.3, 0.99))),
                    label="person",
                    kind="person",
                )
            )
        return dets

    def _faces(self, bgr: Bgr) -> list[Detection]:
        dets: list[Detection] = []
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        for cascade, score in ((self._face, 0.86), (self._profile, 0.72)):
            if cascade.empty():
                continue
            for x, y, w, h in cascade.detectMultiScale(gray, 1.1, 4, minSize=(20, 20)):
                dets.append(Detection(BoundingBox(float(x), float(y), float(w), float(h), score), "face", "person"))
        return dets

    def _cats(self, bgr: Bgr) -> list[Detection]:
        if self._cat.empty():
            return []
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        dets: list[Detection] = []
        for x, y, w, h in self._cat.detectMultiScale(gray, 1.08, 4, minSize=(20, 20)):
            dets.append(Detection(BoundingBox(float(x), float(y), float(w), float(h), 0.7), "cat", "animal"))
        return dets

    def _motion_and_salient(self, bgr: Bgr) -> list[Detection]:
        h, w = bgr.shape[:2]
        fg = self._bg.apply(bgr)
        _, fg = cv2.threshold(fg, 160, 255, cv2.THRESH_BINARY)
        fg = cv2.medianBlur(fg, 5)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
        fused = cv2.bitwise_or(fg, _saliency(bgr))
        contours, _ = cv2.findContours(fused, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dets: list[Detection] = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            area = bw * bh
            if area < 0.0018 * w * h or area > 0.62 * w * h:
                continue
            if bw < 14 or bh < 14:
                continue
            roi = bgr[y : y + bh, x : x + bw]
            label, kind, score = _classify_blob(roi, bw / max(bh, 1), bh / h, area / (w * h), y / h)
            dets.append(
                Detection(
                    box=BoundingBox(float(x), float(y), float(bw), float(bh), score),
                    label=label,
                    kind=kind,
                )
            )
        return dets


def _saliency(bgr: Bgr) -> np.ndarray:
    blur = cv2.GaussianBlur(bgr, (0, 0), 6)
    residual = cv2.absdiff(bgr, blur)
    gray = cv2.cvtColor(residual, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 18, 255, cv2.THRESH_BINARY)
    return cv2.dilate(mask, np.ones((5, 5), np.uint8), 1)


def _classify_blob(roi: np.ndarray, aspect: float, rel_h: float, rel_a: float, rel_y: float) -> tuple[str, str, float]:
    if roi.size == 0:
        return "object", "object", 0.3
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    sat = float(np.mean(s))
    hue = float(np.mean(h))
    val = float(np.mean(v))
    if aspect >= 2.6 and rel_h > 0.08 and rel_a > 0.04:
        return "truck" if rel_h > 0.14 else "bus", "vehicle", 0.56
    if aspect >= 1.55 and rel_h < 0.32:
        if rel_a > 0.025:
            return "car", "vehicle", 0.58
        if rel_h < 0.14:
            return "bicycle" if aspect < 2.3 else "motorcycle", "vehicle", 0.52
        return "car", "vehicle", 0.5
    if 1.12 <= aspect < 1.55 and 0.04 < rel_h < 0.22:
        return "motorcycle", "vehicle", 0.48
    if 0.28 <= aspect <= 0.92 and rel_h > 0.14:
        return "person", "person", 0.52
    fur = (4 <= hue <= 38 and sat > 35) or (sat < 50 and 35 < val < 175)
    if fur and 0.5 <= aspect <= 2.2 and rel_h < 0.28:
        if rel_h < 0.07 and rel_y < 0.58:
            return "bird", "animal", 0.46
        if aspect < 0.9:
            return "cat", "animal", 0.47
        if rel_h > 0.16 and aspect > 1.3:
            return "horse", "animal", 0.48
        if rel_a > 0.03 and aspect > 1.2:
            return "cow", "animal", 0.45
        return "dog", "animal", 0.5
    if rel_h < 0.07 and sat > 55 and rel_y < 0.55:
        return "bird", "animal", 0.42
    if 70 <= hue <= 95 and sat > 50 and rel_h < 0.2:
        return "plant", "object", 0.4
    return "object", "object", 0.34


def _nms(dets: list[Detection], iou_thr: float) -> list[Detection]:
    dets = sorted(dets, key=lambda d: d.box.score, reverse=True)
    keep: list[Detection] = []
    for d in dets:
        drop = False
        for k in keep:
            if d.box.iou(k.box) < iou_thr:
                continue
            if d.kind == k.kind or d.label == k.label or "object" in {d.kind, k.kind}:
                drop = True
                break
        if not drop:
            keep.append(d)
    return keep


def _try_load_ssd():
    paths = ensure_ssd()
    if paths is None:
        return None
    proto, weights = paths
    try:
        net = cv2.dnn.readNetFromCaffe(str(proto), str(weights))
        return net, (300, 300), 127.5
    except Exception:
        return None
