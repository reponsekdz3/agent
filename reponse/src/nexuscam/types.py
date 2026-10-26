from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from numpy.typing import NDArray

Bgr = NDArray[np.uint8]


class TransportKind(str, Enum):
    USB = "usb"
    WIFI_RTSP = "wifi_rtsp"
    WIFI_HTTP = "wifi_http"
    BLUETOOTH_CONTROL = "bluetooth_control"
    SERIAL = "serial"
    DEMO = "demo"


@dataclass(slots=True, frozen=True)
class FramePacket:
    seq: int
    t_ns: int
    bgr: Bgr
    transport: TransportKind
    source_id: str
    dropped_upstream: int = 0


@dataclass(slots=True)
class BoundingBox:
    x: float
    y: float
    w: float
    h: float
    score: float = 1.0

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.x + self.w, self.y + self.h

    @property
    def cxcy(self) -> tuple[float, float]:
        return self.x + self.w * 0.5, self.y + self.h * 0.5

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def iou(self, other: BoundingBox) -> float:
        ax1, ay1, ax2, ay2 = self.xyxy
        bx1, by1, bx2, by2 = other.xyxy
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        inter = iw * ih
        union = self.w * self.h + other.w * other.h - inter
        return inter / union if union > 0 else 0.0

    def as_int(self) -> tuple[int, int, int, int]:
        return int(self.x), int(self.y), int(self.w), int(self.h)


@dataclass(slots=True)
class Detection:
    box: BoundingBox
    label: str
    kind: str


@dataclass(slots=True)
class PersonMeasurement:
    track_id: int
    face_height_m: float | None
    stature_m: float | None
    shoulder_width_m: float | None
    chest_depth_m: float | None
    mass_kg: float | None
    mass_ci95_kg: tuple[float, float] | None
    confidence: float
    notes: str


@dataclass(slots=True)
class KinematicTrack:
    track_id: int
    label: str
    box: BoundingBox
    world_xy_m: tuple[float, float] | None
    speed_mps: float | None
    heading_rad: float | None
    hits: int
    age: int
    extras: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ObjectAnalytics:
    """Per-object operator packet: identity, geometry, motion, class-specific metrics."""

    track_id: int
    label: str
    kind: str
    score: float
    box: BoundingBox
    width_px: float
    height_px: float
    area_px: float
    aspect: float
    world_xy_m: tuple[float, float] | None
    width_m: float | None
    height_m: float | None
    speed_mps: float | None
    speed_kph: float | None
    heading_deg: float | None
    face_height_m: float | None = None
    stature_m: float | None = None
    mass_kg: float | None = None
    mass_uncertainty_kg: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def lines(self) -> list[str]:
        lines = [
            f"ID {self.track_id}  {self.label.upper()}  {self.kind}",
            f"conf {self.score:0.2f}  {self.width_px:0.0f}x{self.height_px:0.0f}px",
        ]
        if self.height_m:
            lines.append(f"size {self.width_m or 0:0.2f} x {self.height_m:0.2f} m")
        if self.speed_kph is not None:
            lines.append(f"speed {self.speed_kph:0.1f} km/h  {self.speed_mps or 0:0.2f} m/s")
        if self.heading_deg is not None:
            lines.append(f"heading {self.heading_deg:0.0f} deg")
        if self.stature_m:
            lines.append(f"height {self.stature_m:0.2f} m")
        if self.face_height_m:
            lines.append(f"face {self.face_height_m * 100:0.1f} cm")
        if self.mass_kg is not None:
            u = self.mass_uncertainty_kg or 0.0
            lines.append(f"mass {self.mass_kg:0.0f} ± {u:0.0f} kg")
        if self.world_xy_m:
            lines.append(f"ground ({self.world_xy_m[0]:0.1f}, {self.world_xy_m[1]:0.1f}) m")
        color = self.extras.get("color")
        if color:
            lines.append(f"color {color}")
        dwell = self.extras.get("dwell_s")
        if dwell:
            lines.append(f"dwell {float(dwell):0.1f} s")
        return lines


@dataclass(slots=True)
class AnalysisResult:
    t_ns: int
    seq: int
    objects: list[ObjectAnalytics]
    people: list[PersonMeasurement]
    kinematics: list[KinematicTrack]
    fps: float
    enhance_ms: float
    vision_ms: float
    source_id: str
    transport: TransportKind
    counts: dict[str, int] = field(default_factory=dict)
