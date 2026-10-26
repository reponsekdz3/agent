from __future__ import annotations

import math

import cv2
import numpy as np

from nexuscam.types import Bgr


def mosaic(labeled: dict[str, Bgr], cell: tuple[int, int] = (640, 360)) -> Bgr:
    if not labeled:
        canvas = np.zeros((cell[1], cell[0], 3), dtype=np.uint8)
        cv2.putText(canvas, "NO CAMERAS", (40, cell[1] // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        return canvas
    n = len(labeled)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    cw, ch = cell
    canvas = np.zeros((rows * ch, cols * cw, 3), dtype=np.uint8)
    for i, (name, frame) in enumerate(labeled.items()):
        r, c = divmod(i, cols)
        resized = cv2.resize(frame, (cw, ch), interpolation=cv2.INTER_AREA)
        y0, x0 = r * ch, c * cw
        canvas[y0 : y0 + ch, x0 : x0 + cw] = resized
        cv2.rectangle(canvas, (x0, y0), (x0 + cw - 1, y0 + ch - 1), (0, 90, 0), 1)
        cv2.putText(
            canvas,
            name[:42],
            (x0 + 8, y0 + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
    return canvas
