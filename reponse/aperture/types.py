from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Transport(str, Enum):
    USB = "usb"
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    SYNTHETIC = "synthetic"


class ObjectClass(str, Enum):
    PERSON = "person"
    FACE = "face"
    CAR = "car"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class CameraIdentity:
    camera_id: str
    name: str
    transport: Transport
    endpoint: str
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    def k_matrix(self) -> list[list[float]]:
        return [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]]


@dataclass(slots=True)
class GroundPlane:
    """World ground plane in camera coordinates: n·X + d = 0, n unit."""

    nx: float = 0.0
    ny: float = 0.0
    nz: float = 1.0
    d: float = 0.0
    meters_per_pixel: float | None = None
    homography: list[list[float]] | None = None


@dataclass(slots=True)
class Detection:
    track_id: int
    cls: ObjectClass
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    keypoints: dict[str, tuple[float, float, float]] = field(default_factory=dict)

    @property
    def cx(self) -> float:
        return 0.5 * (self.x1 + self.x2)

    @property
    def cy(self) -> float:
        return 0.5 * (self.y1 + self.y2)

    @property
    def width(self) -> float:
        return max(1.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(1.0, self.y2 - self.y1)

    @property
    def ground_point(self) -> tuple[float, float]:
        return self.cx, self.y2


@dataclass(slots=True)
class PersonMetrics:
    track_id: int
    height_m: float | None
    face_height_m: float | None
    shoulder_width_m: float | None
    torso_length_m: float | None
    estimated_mass_kg: float | None
    mass_uncertainty_kg: float | None
    method: str
    confidence: float


@dataclass(slots=True)
class KinematicState:
    track_id: int
    cls: ObjectClass
    x_m: float
    y_m: float
    vx_mps: float
    vy_mps: float
    speed_mps: float
    speed_kph: float
    heading_deg: float
    confidence: float


@dataclass(slots=True)
class FramePacket:
    camera_id: str
    frame_index: int
    t_sec: float
    width: int
    height: int
    detections: list[Detection]
    people: list[PersonMetrics]
    kinematics: list[KinematicState]
    enhance_ms: float
    infer_ms: float
    notes: list[str] = field(default_factory=list)
