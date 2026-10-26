from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import orjson


class CommandName(str, Enum):
    HELLO = "hello"
    STREAM_START = "stream.start"
    STREAM_STOP = "stream.stop"
    SET_EXPOSURE = "cam.exposure"
    SET_GAIN = "cam.gain"
    SET_FOCUS = "cam.focus"
    SET_ZOOM = "cam.zoom"
    SET_WB = "cam.white_balance"
    SET_FPS = "cam.fps"
    SET_RESOLUTION = "cam.resolution"
    PTZ = "cam.ptz"
    TORCH = "cam.torch"
    SNAPSHOT = "cam.snapshot"
    STATUS = "sys.status"


@dataclass(slots=True)
class CameraCommand:
    name: CommandName
    camera_id: str
    seq: int
    params: dict[str, Any]

    def to_bytes(self) -> bytes:
        body = {
            "v": 1,
            "name": self.name.value,
            "camera_id": self.camera_id,
            "seq": self.seq,
            "params": self.params,
        }
        return orjson.dumps(body) + b"\n"

    @classmethod
    def from_bytes(cls, raw: bytes) -> CameraCommand:
        data = orjson.loads(raw)
        return cls(
            name=CommandName(data["name"]),
            camera_id=str(data["camera_id"]),
            seq=int(data["seq"]),
            params=dict(data.get("params") or {}),
        )


@dataclass(slots=True)
class CameraAck:
    seq: int
    ok: bool
    camera_id: str
    result: dict[str, Any]

    def to_bytes(self) -> bytes:
        return orjson.dumps(asdict(self)) + b"\n"
