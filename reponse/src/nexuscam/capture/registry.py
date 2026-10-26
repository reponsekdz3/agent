from __future__ import annotations

import logging
from urllib.parse import urlparse

from nexuscam.capture.base import CaptureSource
from nexuscam.capture.opencv_src import OpenCvCapture
from nexuscam.capture.push_src import PushCapture
from nexuscam.capture.synthetic import SyntheticWorldCapture
from nexuscam.capture.usb_enum import UsbCameraInfo, enumerate_usb_cameras
from nexuscam.settings import AppSettings
from nexuscam.types import TransportKind

log = logging.getLogger(__name__)


def discover_phone_http(settings: AppSettings) -> str | None:
    from nexuscam.capture.wifi_scan import USB_TETHER_HOSTS, _tcp_open, discover_wifi_cameras

    ports = tuple(settings.phone.discovery_ports)
    for host in ("127.0.0.1",) + USB_TETHER_HOSTS:
        for port in ports:
            if not _tcp_open(host, port):
                continue
            if port in {554, 8554}:
                return f"rtsp://{host}:{port}/live"
            return f"http://{host}:{port}{settings.phone.preferred_path}"
    hits = discover_wifi_cameras(ports=ports)
    return hits[0].url if hits else None


def open_usb_device(info: UsbCameraInfo, settings: AppSettings) -> OpenCvCapture:
    kind = TransportKind.USB
    sid = info.source_id
    src = OpenCvCapture(info.index, settings.capture, kind, sid)
    src.friendly_name = info.name
    return src


def open_pc_camera(settings: AppSettings) -> CaptureSource:
    cams = enumerate_usb_cameras(settings.capture.max_usb_index)
    if not cams:
        raise RuntimeError("No PC / USB camera found")
    pc = next((c for c in cams if c.is_pc_camera), cams[0])
    return open_usb_device(pc, settings)


def open_source(settings: AppSettings, override: str | None = None) -> CaptureSource:
    cfg = settings.capture
    key = (override or cfg.backend or "auto").strip().lower()

    if key in {"demo", "synthetic"}:
        return SyntheticWorldCapture(cfg)

    if key in {"pc", "webcam", "laptop"}:
        return open_pc_camera(settings)

    if key.startswith("usb:"):
        rest = key.split(":", 1)[1]
        idx = int(rest.split(":")[0])
        return OpenCvCapture(idx, cfg, TransportKind.USB, f"usb:{idx}")

    if key in {"rtsp", "wifi", "wifi_rtsp"} or (key == "auto" and cfg.rtsp_url):
        url = cfg.rtsp_url or (override if override and "://" in override else "")
        if url.startswith("rtsp") or "://" in url:
            kind = TransportKind.WIFI_RTSP if url.startswith("rtsp") else TransportKind.WIFI_HTTP
            return OpenCvCapture(url, cfg, kind, f"net:{url}")

    if key in {"http", "phone", "wifi_http"}:
        url = cfg.rtsp_url or discover_phone_http(settings)
        if not url:
            raise RuntimeError("No phone HTTP/RTSP endpoint found on Wi-Fi or USB tether")
        kind = TransportKind.WIFI_RTSP if url.startswith("rtsp") else TransportKind.WIFI_HTTP
        return OpenCvCapture(url, cfg, kind, f"net:{url}")

    if key in {"push", "browser", "ingress"}:
        return PushCapture("push:browser", TransportKind.WIFI_HTTP)

    if "://" in key:
        parsed = urlparse(key)
        kind = TransportKind.WIFI_RTSP if parsed.scheme == "rtsp" else TransportKind.WIFI_HTTP
        return OpenCvCapture(key, cfg, kind, f"net:{key}")

    if key in {"usb", "auto"}:
        cams = enumerate_usb_cameras(cfg.max_usb_index)
        if cams:
            target = next((c for c in cams if c.index == cfg.device_index), cams[0])
            return open_usb_device(target, settings)
        if key == "usb" or cfg.strict_capture:
            # last try configured index
            return OpenCvCapture(cfg.device_index, cfg, TransportKind.USB, f"usb:{cfg.device_index}")
        log.info("No USB camera; using synthetic range")
        return SyntheticWorldCapture(cfg)

    log.info("Unknown backend %r — using synthetic range", key)
    return SyntheticWorldCapture(cfg)
