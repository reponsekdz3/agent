from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass

from aperture.types import CameraIdentity, Transport

log = logging.getLogger("aperture.capture.ble")

APERTURE_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
APERTURE_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
APERTURE_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


@dataclass(slots=True)
class PhoneBridge:
    """Phone discovered over BLE that advertises a Wi-Fi/USB video endpoint."""

    address: str
    name: str
    stream_url: str | None
    control_host: str | None
    control_port: int | None
    write_uuid: str = APERTURE_RX
    identity: CameraIdentity | None = None


def _decode_manufacturer(payload: bytes) -> dict[str, str | int]:
    """Aperture advertises: magic 'APV1' + ipv4 + port + flags."""
    out: dict[str, str | int] = {}
    if len(payload) >= 10 and payload[:4] == b"APV1":
        ip = ".".join(str(b) for b in payload[4:8])
        port = struct.unpack_from(">H", payload, 8)[0]
        out["ip"] = ip
        out["port"] = int(port)
        out["stream_url"] = f"http://{ip}:{port}/mjpeg"
        out["control_host"] = ip
        out["control_port"] = int(port) + 1
    return out


async def scan_phone_bridges(timeout: float = 6.0, service_uuid: str | None = None) -> list[PhoneBridge]:
    try:
        from bleak import BleakScanner
    except ImportError:
        log.warning("bleak missing; BLE scan skipped")
        return []

    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    found: list[PhoneBridge] = []
    want = (service_uuid or APERTURE_SERVICE).lower()
    for device, adv in devices.values():
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        mfg = {}
        for _, value in (adv.manufacturer_data or {}).items():
            mfg.update(_decode_manufacturer(bytes(value)))
        if want not in uuids and "APV" not in (device.name or "") and not mfg:
            continue
        stream = mfg.get("stream_url")
        if isinstance(stream, int):
            stream = None
        identity = CameraIdentity(
            camera_id=f"bt:{device.address}",
            name=device.name or f"BLE phone {device.address}",
            transport=Transport.BLUETOOTH,
            endpoint=str(stream or device.address),
            capabilities=("stream.start", "exposure", "torch", "zoom"),
            metadata={"ble_address": device.address, **{k: str(v) for k, v in mfg.items()}},
        )
        found.append(
            PhoneBridge(
                address=device.address,
                name=device.name or device.address,
                stream_url=str(stream) if stream else None,
                control_host=str(mfg["control_host"]) if "control_host" in mfg else None,
                control_port=int(mfg["control_port"]) if "control_port" in mfg else None,
                identity=identity,
            )
        )
    return found


def scan_phone_bridges_sync(timeout: float = 6.0) -> list[PhoneBridge]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(scan_phone_bridges(timeout=timeout))
    fut = asyncio.run_coroutine_threadsafe(scan_phone_bridges(timeout=timeout), loop)
    return fut.result(timeout=timeout + 4)
