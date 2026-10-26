from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787


class CaptureCfg(BaseModel):
    backend: str = "auto"
    device_index: int = 0
    rtsp_url: str = ""
    width: int = 1280
    height: int = 720
    fps: int = 30
    buffer_size: int = 2
    strict_capture: bool = False
    auto_open_all_usb: bool = True
    include_pc_camera: bool = True
    max_usb_index: int = 12
    wifi_scan_on_start: bool = False


class BluetoothCfg(BaseModel):
    enabled: bool = True
    service_uuid: str = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    advertise_name: str = "NexusCam-Link"


class PhoneCfg(BaseModel):
    discovery_ports: list[int] = Field(default_factory=lambda: [8080, 4747, 8081, 8554])
    preferred_path: str = "/video"


class EnhanceCfg(BaseModel):
    enabled: bool = True
    clahe_clip: float = 2.4
    clahe_grid: int = 8
    unsharp_amount: float = 0.55
    unsharp_radius: float = 1.2
    temporal_alpha: float = 0.35
    denoise_h: float = 0.0
    auto_white_balance: bool = True
    gamma: float = 1.05


class VisionCfg(BaseModel):
    detect_people: bool = True
    detect_vehicles: bool = True
    detect_animals: bool = True
    detect_objects: bool = True
    min_track_hits: int = 1
    max_track_age: int = 22
    iou_match: float = 0.28
    speed_smooth: float = 0.45
    dnn_model: str = ""
    dnn_config: str = ""
    dnn_labels: list[str] = Field(default_factory=list)
    allow_online_enrichment: bool = False
    min_score: float = 0.28


class CalibrationCfg(BaseModel):
    fx: float = 1200.0
    fy: float = 1200.0
    cx: float = 640.0
    cy: float = 360.0
    homography: list[list[float]] = Field(
        default_factory=lambda: [
            [0.0042, 0.0, -2.1],
            [0.0, 0.0038, -0.4],
            [0.0, 0.0008, 1.0],
        ]
    )
    assumed_body_density_kg_m3: float = 985.0
    reference_face_height_m: float = 0.185


class ControlCfg(BaseModel):
    allow_usb_props: bool = True
    onvif_cgi_base: str = ""


class AppSettings(BaseModel):
    server: ServerCfg = Field(default_factory=ServerCfg)
    capture: CaptureCfg = Field(default_factory=CaptureCfg)
    bluetooth: BluetoothCfg = Field(default_factory=BluetoothCfg)
    phone: PhoneCfg = Field(default_factory=PhoneCfg)
    enhance: EnhanceCfg = Field(default_factory=EnhanceCfg)
    vision: VisionCfg = Field(default_factory=VisionCfg)
    calibration: CalibrationCfg = Field(default_factory=CalibrationCfg)
    control: ControlCfg = Field(default_factory=ControlCfg)

    @classmethod
    def load(cls, path: str | Path | None = None) -> AppSettings:
        if path is None:
            candidate = Path("config/default.yaml")
            path = candidate if candidate.exists() else None
        if path is None:
            return cls()
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)
