from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from aperture.types import CameraIdentity


class FrameSource(ABC):
    identity: CameraIdentity

    @abstractmethod
    def open(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray | None]:
        raise NotImplementedError

    @abstractmethod
    def apply_params(self, params: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @property
    def backend_handle(self):
        return None
