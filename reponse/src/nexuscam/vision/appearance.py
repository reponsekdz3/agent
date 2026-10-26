from __future__ import annotations

import cv2
import numpy as np

from nexuscam.types import Bgr, BoundingBox


def dominant_color_bgr(bgr: Bgr, box: BoundingBox) -> tuple[int, int, int]:
    x, y, w, h = box.as_int()
    h_img, w_img = bgr.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(w_img, x + max(w, 1)), min(h_img, y + max(h, 1))
    roi = bgr[y1:y2, x1:x2]
    if roi.size < 30:
        return 0, 0, 0
    try:
        small = cv2.resize(roi, (24, 24), interpolation=cv2.INTER_AREA)
        pixels = small.reshape(-1, 3).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 8, 1.0)
        _, labels, centers = cv2.kmeans(pixels, 2, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
        counts = np.bincount(labels.flatten(), minlength=2)
        center = centers[int(np.argmax(counts))]
        return int(center[0]), int(center[1]), int(center[2])
    except Exception:
        mean = roi.reshape(-1, 3).mean(axis=0)
        return int(mean[0]), int(mean[1]), int(mean[2])


def color_name(bgr_tuple: tuple[int, int, int]) -> str:
    b, g, r = bgr_tuple
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0, 0]
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
    if v < 45:
        return "black"
    if s < 35:
        return "white" if v > 180 else "gray"
    if h < 12 or h >= 168:
        return "red"
    if h < 22:
        return "orange"
    if h < 38:
        return "yellow"
    if h < 85:
        return "green"
    if h < 130:
        return "blue"
    return "purple"
