from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from aperture.types import Detection, ObjectClass


@dataclass
class _CascadeSet:
    face: cv2.CascadeClassifier
    fullbody: cv2.CascadeClassifier
    upper: cv2.CascadeClassifier


def _load_cascades() -> _CascadeSet | None:
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    full = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_fullbody.xml")
    upper = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_upperbody.xml")
    if face.empty() or full.empty():
        return None
    return _CascadeSet(face=face, fullbody=full, upper=upper)


class SceneDetector:
    """CPU detector: Haar bodies/faces + color/motion vehicle proposals.

    Production deployments can swap this for an ONNX YOLO backend; the rest of
    the pipeline consumes Detection objects only.
    """

    def __init__(self) -> None:
        self._casc = _load_cascades()
        self._fg = cv2.createBackgroundSubtractorMOG2(history=400, varThreshold=16, detectShadows=False)
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, bgr: np.ndarray) -> list[Detection]:
        h, w = bgr.shape[:2]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        out: list[Detection] = []
        out.extend(self._people(gray, w, h))
        out.extend(self._faces(gray, out))
        out.extend(self._vehicles(bgr, gray))
        return self._nms(out)

    def _people(self, gray: np.ndarray, w: int, h: int) -> list[Detection]:
        dets: list[Detection] = []
        rects, weights = self._hog.detectMultiScale(gray, winStride=(8, 8), padding=(8, 8), scale=1.07)
        for (x, y, bw, bh), score in zip(rects, weights.reshape(-1) if len(weights) else []):
            dets.append(
                Detection(
                    track_id=-1,
                    cls=ObjectClass.PERSON,
                    x1=float(x),
                    y1=float(y),
                    x2=float(x + bw),
                    y2=float(y + bh),
                    score=float(np.clip(score / 3.0, 0.15, 0.99)),
                )
            )
        if self._casc is not None and len(dets) < 2:
            for x, y, bw, bh in self._casc.fullbody.detectMultiScale(gray, 1.05, 3, minSize=(24, 60)):
                dets.append(
                    Detection(
                        track_id=-1,
                        cls=ObjectClass.PERSON,
                        x1=float(x),
                        y1=float(y),
                        x2=float(x + bw),
                        y2=float(y + bh),
                        score=0.45,
                    )
                )
        return dets

    def _faces(self, gray: np.ndarray, people: list[Detection]) -> list[Detection]:
        if self._casc is None:
            return []
        faces = []
        for x, y, bw, bh in self._casc.face.detectMultiScale(gray, 1.12, 5, minSize=(28, 28)):
            kp = {
                "forehead": (x + bw * 0.5, y + bh * 0.18, 0.8),
                "chin": (x + bw * 0.5, y + bh * 0.92, 0.8),
                "left_eye": (x + bw * 0.32, y + bh * 0.38, 0.6),
                "right_eye": (x + bw * 0.68, y + bh * 0.38, 0.6),
            }
            faces.append(
                Detection(
                    track_id=-1,
                    cls=ObjectClass.FACE,
                    x1=float(x),
                    y1=float(y),
                    x2=float(x + bw),
                    y2=float(y + bh),
                    score=0.7,
                    keypoints=kp,
                )
            )
        if not faces:
            # Approximate a face box from the upper 18% of a person detection.
            for p in people:
                if p.cls != ObjectClass.PERSON:
                    continue
                fh = p.height * 0.18
                fw = p.width * 0.42
                cx = p.cx
                y1 = p.y1 + p.height * 0.02
                faces.append(
                    Detection(
                        track_id=-1,
                        cls=ObjectClass.FACE,
                        x1=cx - fw / 2,
                        y1=y1,
                        x2=cx + fw / 2,
                        y2=y1 + fh,
                        score=0.35,
                        keypoints={
                            "forehead": (cx, y1 + fh * 0.18, 0.4),
                            "chin": (cx, y1 + fh * 0.92, 0.4),
                        },
                    )
                )
        return faces

    def _vehicles(self, bgr: np.ndarray, gray: np.ndarray) -> list[Detection]:
        mask = self._fg.apply(bgr)
        mask = cv2.medianBlur(mask, 5)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.dilate(mask, np.ones((7, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = gray.shape[:2]
        dets: list[Detection] = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            area = bw * bh
            if area < 900 or bh < 16 or bw < 24:
                continue
            if y < h * 0.28:
                continue
            ar = bw / max(1, bh)
            roi = bgr[y : y + bh, x : x + bw]
            cls, score = self._classify_vehicle(roi, ar, bh / h)
            if cls is None:
                continue
            dets.append(
                Detection(
                    track_id=-1,
                    cls=cls,
                    x1=float(x),
                    y1=float(y),
                    x2=float(x + bw),
                    y2=float(y + bh),
                    score=score,
                )
            )
        return dets

    @staticmethod
    def _classify_vehicle(roi: np.ndarray, aspect: float, rel_h: float) -> tuple[ObjectClass | None, float]:
        if roi.size == 0:
            return None, 0.0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        sat = float(np.mean(hsv[:, :, 1]))
        # Aspect-ratio priors from typical roadside cameras
        if 1.7 <= aspect <= 4.2 and rel_h > 0.04:
            return ObjectClass.CAR, 0.55 + 0.002 * min(sat, 80)
        if 1.15 <= aspect < 1.7 and rel_h > 0.03:
            return ObjectClass.MOTORCYCLE, 0.5
        if 0.55 <= aspect < 1.15 and rel_h > 0.035:
            return ObjectClass.BICYCLE, 0.48
        if aspect > 4.2:
            return ObjectClass.CAR, 0.4
        return None, 0.0

    @staticmethod
    def _nms(dets: list[Detection], iou_thr: float = 0.45) -> list[Detection]:
        if not dets:
            return []
        keep: list[Detection] = []
        order = sorted(dets, key=lambda d: d.score, reverse=True)
        while order:
            best = order.pop(0)
            keep.append(best)
            order = [d for d in order if d.cls != best.cls or _iou(best, d) < iou_thr]
        return keep


def _iou(a: Detection, b: Detection) -> float:
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a.width * a.height + b.width * b.height - inter
    return inter / union if union > 0 else 0.0
