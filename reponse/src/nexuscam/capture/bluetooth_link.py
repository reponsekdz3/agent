from __future__ import annotations

import asyncio
import json
import logging
import struct
import threading
from dataclasses import dataclass, field
from typing import Any

from nexuscam.settings import BluetoothCfg

log = logging.getLogger(__name__)

NORDIC_UART_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NORDIC_UART_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

PHONE_HINTS = (
    "iphone",
    "android",
    "pixel",
    "galaxy",
    "nexuscam",
    "droidcam",
    "ipwebcam",
    "ip webcam",
    "oneplus",
    "xiaomi",
    "redmi",
    "huawei",
    "oppo",
    "vivo",
    "samsung",
)


@dataclass
class BleDevice:
    name: str
    address: str
    rssi: int | None = None
    stream_url: str = ""
    service_uuids: list[str] = field(default_factory=list)


@dataclass
class PhoneLinkState:
    connected: bool = False
    device_name: str = ""
    address: str = ""
    negotiated_url: str = ""
    transport: str = ""
    last_telemetry: dict[str, Any] = field(default_factory=dict)
    devices: list[dict[str, Any]] = field(default_factory=list)


def decode_advertisement(payload: bytes) -> dict[str, Any]:
    """Aperture/NexusCam BLE advert: magic APV1 + IPv4 + port."""
    out: dict[str, Any] = {}
    if len(payload) >= 10 and payload[:4] == b"APV1":
        ip = ".".join(str(b) for b in payload[4:8])
        port = struct.unpack_from(">H", payload, 8)[0]
        out["ip"] = ip
        out["port"] = int(port)
        out["stream_url"] = f"http://{ip}:{port}/video"
    else:
        try:
            text = payload.decode("utf-8", errors="ignore").strip()
            if text.startswith("{"):
                out.update(json.loads(text))
            elif "://" in text:
                out["stream_url"] = text
        except Exception:
            pass
    return out


class BluetoothControlPlane:
    """BLE is the control/discovery plane. Video rides Wi-Fi, USB tether, or WS ingress."""

    def __init__(self, cfg: BluetoothCfg) -> None:
        self.cfg = cfg
        self.state = PhoneLinkState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.cfg.enabled:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ble-control", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def snapshot(self) -> PhoneLinkState:
        with self._lock:
            return PhoneLinkState(
                connected=self.state.connected,
                device_name=self.state.device_name,
                address=self.state.address,
                negotiated_url=self.state.negotiated_url,
                transport=self.state.transport,
                last_telemetry=dict(self.state.last_telemetry),
                devices=list(self.state.devices),
            )

    def _run(self) -> None:
        try:
            asyncio.run(self._scan_loop())
        except Exception:
            log.exception("Bluetooth control plane stopped")

    async def _scan_loop(self) -> None:
        try:
            from bleak import BleakScanner
        except ImportError:
            log.warning("bleak not installed; Bluetooth discovery disabled")
            return

        while not self._stop.is_set():
            try:
                devices = await self._discover(BleakScanner)
                with self._lock:
                    self.state.devices = [
                        {
                            "name": d.name,
                            "address": d.address,
                            "rssi": d.rssi,
                            "stream_url": d.stream_url,
                            "service_uuids": d.service_uuids,
                        }
                        for d in devices
                    ]
                    phones = [d for d in devices if _looks_like_phone(d)]
                    if phones:
                        best = phones[0]
                        self.state.connected = True
                        self.state.device_name = best.name
                        self.state.address = best.address
                        if best.stream_url:
                            self.state.negotiated_url = best.stream_url
                            self.state.transport = "wifi_http"
                for d in devices:
                    if d.stream_url:
                        log.info("BLE advertised stream %s from %s", d.stream_url, d.name)
            except Exception as exc:
                log.debug("BLE scan failed: %s", exc)
            await asyncio.sleep(4.0)

    async def _discover(self, scanner_cls: Any) -> list[BleDevice]:
        found: list[BleDevice] = []
        try:
            advertised = await scanner_cls.discover(timeout=3.2, return_adv=True)
        except TypeError:
            raw = await scanner_cls.discover(timeout=3.2)
            advertised = {getattr(d, "address", str(i)): (d, None) for i, d in enumerate(raw)}
        except Exception as exc:
            log.debug("BLE discover error: %s", exc)
            return []

        for item in advertised.values() if isinstance(advertised, dict) else []:
            if isinstance(item, tuple) and len(item) == 2:
                device, adv = item
            else:
                device, adv = item, None
            name = getattr(device, "name", None) or ""
            address = getattr(device, "address", "") or ""
            rssi = getattr(adv, "rssi", None) if adv is not None else getattr(device, "rssi", None)
            uuids = []
            stream = ""
            if adv is not None:
                uuids = [str(u).lower() for u in (getattr(adv, "service_uuids", None) or [])]
                mfg = getattr(adv, "manufacturer_data", None) or {}
                for _, value in mfg.items():
                    decoded = decode_advertisement(bytes(value))
                    stream = str(decoded.get("stream_url") or stream)
            found.append(
                BleDevice(name=name or address, address=address, rssi=rssi, stream_url=stream, service_uuids=uuids)
            )
        return found

    async def read_gatt_url(self, address: str) -> str | None:
        try:
            from bleak import BleakClient
        except ImportError:
            return None
        try:
            async with BleakClient(address, timeout=8.0) as client:
                for uuid in (NORDIC_UART_TX, NORDIC_UART_RX, self.cfg.service_uuid):
                    try:
                        raw = await client.read_gatt_char(uuid)
                    except Exception:
                        continue
                    decoded = decode_advertisement(bytes(raw))
                    url = decoded.get("stream_url")
                    if url:
                        return str(url)
                    text = bytes(raw).decode("utf-8", errors="ignore")
                    if "://" in text:
                        return text.strip()
        except Exception as exc:
            log.debug("GATT read failed for %s: %s", address, exc)
        return None

    def gatt_url_sync(self, address: str) -> str | None:
        try:
            return asyncio.run(self.read_gatt_url(address))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.read_gatt_url(address))
            finally:
                loop.close()

    def ingest_handshake(self, payload: dict[str, Any]) -> PhoneLinkState:
        url = payload.get("stream_url") or payload.get("url") or ""
        transport = payload.get("transport") or "wifi_http"
        with self._lock:
            self.state.connected = True
            self.state.device_name = str(payload.get("name") or self.state.device_name)
            self.state.address = str(payload.get("address") or self.state.address)
            if url:
                self.state.negotiated_url = str(url)
            self.state.transport = str(transport)
            self.state.last_telemetry = payload
            return self.snapshot()

    def encode_announce(self, host: str, port: int) -> bytes:
        body = {
            "v": 1,
            "service": self.cfg.advertise_name,
            "control": f"http://{host}:{port}/api/v1/link/phone",
            "phone_ui": f"http://{host}:{port}/phone",
            "note": "Open the phone UI or POST a stream_url to attach the camera.",
        }
        return json.dumps(body).encode("utf-8")


def _looks_like_phone(d: BleDevice) -> bool:
    blob = f"{d.name} {' '.join(d.service_uuids)}".lower()
    if d.stream_url:
        return True
    return any(k in blob for k in PHONE_HINTS)
