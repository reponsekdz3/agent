from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APERTURE_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8787
    jpeg_quality: int = 82
    target_fps: float = 30.0
    usb_index: int = 0
    rtsp_url: str | None = None
    mjpeg_url: str | None = None
    bluetooth_scan_sec: float = 6.0
    ble_service_uuid: str = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    synthetic: bool = True
    enhance: bool = True
    detect: bool = True
    measure: bool = True
    speed: bool = True
    camera_height_m: float = 6.5
    camera_tilt_deg: float = 28.0
    focal_px: float | None = None
    ground_mpp: float | None = None
    record_dir: str = "recordings"
    max_tracks: int = 64
    person_density_kg_m3: float = 985.0
    enable_ble: bool = True
    log_json: bool = True

    enhance_temporal: float = 0.35
    enhance_clip_limit: float = 2.4
    enhance_sharpen: float = 0.55
    enhance_dehaze: float = 0.18

    vehicle_classes: tuple[str, ...] = Field(
        default=("car", "motorcycle", "bicycle")
    )
