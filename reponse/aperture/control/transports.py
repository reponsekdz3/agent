from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod

from aperture.control.protocol import CameraAck, CameraCommand
from aperture.types import Transport

log = logging.getLogger("aperture.control")


class CommandTransport(ABC):
    kind: Transport

    @abstractmethod
    async def send(self, command: CameraCommand) -> CameraAck:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class LoopbackTransport(CommandTransport):
    """Local USB / synthetic cameras: apply commands in-process."""

    kind = Transport.USB

    def __init__(self) -> None:
        self.state: dict[str, dict] = {}

    async def send(self, command: CameraCommand) -> CameraAck:
        slot = self.state.setdefault(command.camera_id, {})
        slot.update(command.params)
        slot["last_command"] = command.name.value
        return CameraAck(seq=command.seq, ok=True, camera_id=command.camera_id, result=dict(slot))


class TcpTransport(CommandTransport):
    kind = Transport.WIFI

    def __init__(self, host: str, port: int, timeout: float = 2.5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock = asyncio.Lock()

    async def send(self, command: CameraCommand) -> CameraAck:
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=self.timeout
                )
            except Exception as exc:
                return CameraAck(
                    seq=command.seq,
                    ok=False,
                    camera_id=command.camera_id,
                    result={"error": str(exc), "endpoint": f"{self.host}:{self.port}"},
                )
            try:
                writer.write(command.to_bytes())
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
                if not line:
                    return CameraAck(
                        seq=command.seq,
                        ok=False,
                        camera_id=command.camera_id,
                        result={"error": "empty ack"},
                    )
                import orjson

                data = orjson.loads(line)
                return CameraAck(
                    seq=int(data.get("seq", command.seq)),
                    ok=bool(data.get("ok", True)),
                    camera_id=str(data.get("camera_id", command.camera_id)),
                    result=dict(data.get("result") or {}),
                )
            except Exception as exc:
                return CameraAck(
                    seq=command.seq,
                    ok=False,
                    camera_id=command.camera_id,
                    result={"error": str(exc)},
                )
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()


class BleTransport(CommandTransport):
    kind = Transport.BLUETOOTH

    def __init__(self, address: str, write_uuid: str, notify_uuid: str | None = None) -> None:
        self.address = address
        self.write_uuid = write_uuid
        self.notify_uuid = notify_uuid

    async def send(self, command: CameraCommand) -> CameraAck:
        try:
            from bleak import BleakClient
        except ImportError:
            return CameraAck(
                seq=command.seq,
                ok=False,
                camera_id=command.camera_id,
                result={"error": "bleak is not installed"},
            )
        try:
            async with BleakClient(self.address, timeout=8.0) as client:
                await client.write_gatt_char(self.write_uuid, command.to_bytes(), response=True)
                return CameraAck(
                    seq=command.seq,
                    ok=True,
                    camera_id=command.camera_id,
                    result={"address": self.address},
                )
        except Exception as exc:
            log.warning("BLE command failed: %s", exc)
            return CameraAck(
                seq=command.seq,
                ok=False,
                camera_id=command.camera_id,
                result={"error": str(exc), "address": self.address},
            )
