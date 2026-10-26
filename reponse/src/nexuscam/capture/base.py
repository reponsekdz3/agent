from __future__ import annotations

from abc import ABC, abstractmethod

from nexuscam.types import FramePacket


class CaptureError(RuntimeError):
    pass


class CaptureSource(ABC):
    source_id: str

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def read(self, seq: int) -> FramePacket | None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def set_property(self, name: str, value: float) -> bool:
        return False

    def get_property(self, name: str) -> float | None:
        return None
