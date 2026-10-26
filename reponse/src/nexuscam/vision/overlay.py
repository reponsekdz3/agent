from __future__ import annotations

import cv2

from nexuscam.types import AnalysisResult, Bgr, ObjectAnalytics

GREEN = (0, 255, 0)
GREEN_DIM = (0, 70, 0)
WHITE = (235, 255, 235)
BLACK = (8, 20, 8)


def draw_analytics(bgr: Bgr, result: AnalysisResult) -> Bgr:
    vis = bgr.copy()
    h, w = vis.shape[:2]
    for obj in result.objects:
        _box(vis, obj)
    _hud(vis, result, w, h)
    return vis


def _box(vis: Bgr, obj: ObjectAnalytics) -> None:
    x, y, bw, bh = obj.box.as_int()
    x2, y2 = x + max(bw, 2), y + max(bh, 2)
    cv2.rectangle(vis, (x, y), (x2, y2), GREEN, 2, cv2.LINE_AA)
    tick = max(10, min(bw, bh) // 5)
    for cx, cy, sx, sy in (
        (x, y, 1, 1),
        (x2, y, -1, 1),
        (x, y2, 1, -1),
        (x2, y2, -1, -1),
    ):
        cv2.line(vis, (cx, cy), (cx + sx * tick, cy), GREEN, 3, cv2.LINE_AA)
        cv2.line(vis, (cx, cy), (cx, cy + sy * tick), GREEN, 3, cv2.LINE_AA)
    lines = obj.lines()
    tw = max(cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, 0.43, 1)[0][0] for s in lines) + 14
    th = 17 * len(lines) + 10
    tx, ty = x, max(0, y - th - 6)
    if ty < 2:
        ty = min(vis.shape[0] - th - 2, y2 + 4)
    if tx + tw > vis.shape[1]:
        tx = max(0, vis.shape[1] - tw - 2)
    overlay = vis.copy()
    cv2.rectangle(overlay, (tx, ty), (tx + tw, ty + th), GREEN_DIM, -1)
    cv2.addWeighted(overlay, 0.78, vis, 0.22, 0, vis)
    cv2.rectangle(vis, (tx, ty), (tx + tw, ty + th), GREEN, 1, cv2.LINE_AA)
    for i, line in enumerate(lines):
        cv2.putText(
            vis,
            line,
            (tx + 6, ty + 18 + i * 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            WHITE,
            1,
            cv2.LINE_AA,
        )


def _hud(vis: Bgr, result: AnalysisResult, width: int, height: int) -> None:
    counts = result.counts or {}
    kind_bits = "  ".join(
        f"{k}:{v}" for k, v in sorted(counts.items()) if k in {"person", "vehicle", "animal", "object"} and v
    )
    label_bits = "  ".join(
        f"{k}:{v}"
        for k, v in sorted(counts.items())
        if k not in {"person", "vehicle", "animal", "object"} and v
    )
    lines = [
        "NEXUSCAM  LIVE ANALYTICS",
        f"{result.source_id}  {result.transport.value}  {result.fps:0.1f} fps",
        f"enhance {result.enhance_ms:0.1f}ms  vision {result.vision_ms:0.1f}ms  tracks {len(result.objects)}",
        kind_bits or "kinds: —",
        label_bits[:96] or "labels: —",
    ]
    panel_w = min(width - 16, 680)
    panel_h = 22 * len(lines) + 12
    overlay = vis.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), BLACK, -1)
    cv2.addWeighted(overlay, 0.7, vis, 0.3, 0, vis)
    cv2.rectangle(vis, (8, 8), (8 + panel_w, 8 + panel_h), GREEN, 1, cv2.LINE_AA)
    for i, line in enumerate(lines):
        cv2.putText(vis, line, (16, 28 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, GREEN, 1, cv2.LINE_AA)
