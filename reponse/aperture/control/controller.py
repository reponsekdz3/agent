from __future__ import annotations

import itertools
from typing import Any

from aperture.control.protocol import CameraAck, CameraCommand, CommandName
from aperture.control.transports import CommandTransport
from aperture.types import CameraIdentity


class CameraController:
    """Unified command plane for USB, Wi-Fi, and Bluetooth cameras."""

    def __init__(self) -> None:
        self._seq = itertools.count(1)
        self._transports: dict[str, CommandTransport] = {}
        self._identities: dict[str, CameraIdentity] = {}

    def attach(self, identity: CameraIdentity, transport: CommandTransport) -> None:
        self._identities[identity.camera_id] = identity
        self._transports[identity.camera_id] = transport

    def detach(self, camera_id: str) -> None:
        self._transports.pop(camera_id, None)
        self._identities.pop(camera_id, None)

    def list_cameras(self) -> list[CameraIdentity]:
        return list(self._identities.values())

    async def command(
        self, camera_id: str, name: CommandName | str, params: dict[str, Any] | None = None
    ) -> CameraAck:
        transport = self._transports.get(camera_id)
        if transport is None:
            return CameraAck(
                seq=0,
                ok=False,
                camera_id=camera_id,
                result={"error": "unknown camera"},
            )
        cmd = CameraCommand(
            name=CommandName(name) if not isinstance(name, CommandName) else name,
            camera_id=camera_id,
            seq=next(self._seq),
            params=params or {},
        )
        return await transport.send(cmd)

    async def close(self) -> None:
        for t in self._transports.values():
            await t.close()
        self._transports.clear()
