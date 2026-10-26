from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from nexuscam.capture.base import CaptureSource
from nexuscam.settings import AppSettings

log = logging.getLogger(__name__)

USB_PROPS = (
    "brightness",
    "contrast",
    "saturation",
    "hue",
    "gain",
    "exposure",
    "focus",
    "zoom",
    "pan",
    "tilt",
    "autofocus",
    "auto_exposure",
    "fps",
    "width",
    "height",
)


class CameraRig:
    """High-level camera command plane: USB UVC, Wi-Fi CGI/ONVIF-style, serial PTZ."""

    def __init__(self, settings: AppSettings, source: CaptureSource | None = None) -> None:
        self.settings = settings
        self.source = source
        self.last_ack: dict[str, Any] = {}

    def attach(self, source: CaptureSource) -> None:
        self.source = source

    def list_serial_ports(self) -> list[dict[str, str]]:
        try:
            import serial.tools.list_ports
        except ImportError:
            return []
        ports = []
        for p in serial.tools.list_ports.comports():
            ports.append({"device": p.device, "description": p.description or "", "hwid": p.hwid or ""})
        return ports

    def get_usb_state(self) -> dict[str, float | None]:
        if self.source is None:
            return {}
        return {name: self.source.get_property(name) for name in USB_PROPS}

    def set(self, name: str, value: float) -> dict[str, Any]:
        ok = False
        if self.settings.control.allow_usb_props and self.source is not None:
            ok = self.source.set_property(name, value)
        cgi = self.settings.control.onvif_cgi_base.strip()
        remote = False
        if cgi:
            remote = self._cgi(name, value, cgi)
        self.last_ack = {"name": name, "value": value, "usb": ok, "wifi": remote}
        return self.last_ack

    def ptz(self, pan: float = 0.0, tilt: float = 0.0, zoom: float = 0.0) -> dict[str, Any]:
        results = {}
        if pan:
            results["pan"] = self.set("pan", pan)
        if tilt:
            results["tilt"] = self.set("tilt", tilt)
        if zoom:
            results["zoom"] = self.set("zoom", zoom)
        cgi = self.settings.control.onvif_cgi_base.strip()
        if cgi and (pan or tilt):
            code = "Left" if pan < 0 else "Right" if pan > 0 else ("Up" if tilt > 0 else "Down")
            try:
                url = f"{cgi.rstrip('/')}/ptz.cgi?{urlencode({'action': 'start', 'code': code})}"
                urlopen(url, timeout=1.2).read(64)
                results["cgi_ptz"] = code
            except Exception as exc:
                results["cgi_error"] = str(exc)
        return results

    def _cgi(self, name: str, value: float, base: str) -> bool:
        try:
            url = f"{base.rstrip('/')}/config?{urlencode({name: value})}"
            urlopen(url, timeout=1.2).read(128)
            return True
        except Exception as exc:
            log.debug("Wi-Fi camera CGI failed: %s", exc)
            return False
