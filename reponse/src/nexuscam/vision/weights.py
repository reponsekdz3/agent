from __future__ import annotations

import logging
from pathlib import Path
from urllib.request import urlopen

log = logging.getLogger(__name__)

_PROTO = (
    "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/"
    "master/MobileNetSSD_deploy.prototxt"
)
_WEIGHTS = (
    "https://github.com/chuanqi305/MobileNet-SSD/raw/master/MobileNetSSD_deploy.caffemodel"
)

SSD_NAMES = {
    1: "aeroplane",
    2: "bicycle",
    3: "bird",
    4: "boat",
    5: "bottle",
    6: "bus",
    7: "car",
    8: "cat",
    9: "chair",
    10: "cow",
    11: "diningtable",
    12: "dog",
    13: "horse",
    14: "motorbike",
    15: "person",
    16: "pottedplant",
    17: "sheep",
    18: "sofa",
    19: "train",
    20: "tvmonitor",
}

KIND_OF = {
    "person": "person",
    "bicycle": "vehicle",
    "car": "vehicle",
    "motorbike": "vehicle",
    "motorcycle": "vehicle",
    "bus": "vehicle",
    "train": "vehicle",
    "aeroplane": "vehicle",
    "boat": "vehicle",
    "bird": "animal",
    "cat": "animal",
    "cow": "animal",
    "dog": "animal",
    "horse": "animal",
    "sheep": "animal",
    "bottle": "object",
    "chair": "object",
    "diningtable": "object",
    "pottedplant": "object",
    "sofa": "object",
    "tvmonitor": "object",
}

DISPLAY = {
    "motorbike": "motorcycle",
    "aeroplane": "airplane",
    "diningtable": "table",
    "pottedplant": "plant",
    "tvmonitor": "screen",
}


def models_dir() -> Path:
    root = Path.cwd() / "models"
    root.mkdir(exist_ok=True)
    return root


def ensure_ssd(download: bool = False, timeout: float = 25.0) -> tuple[Path, Path] | None:
    d = models_dir()
    proto = d / "MobileNetSSD_deploy.prototxt"
    weights = d / "MobileNetSSD_deploy.caffemodel"
    if download:
        try:
            if not proto.exists() or proto.stat().st_size < 1000:
                _fetch(_PROTO, proto, timeout)
            if not weights.exists() or weights.stat().st_size < 1_000_000:
                _fetch(_WEIGHTS, weights, timeout)
        except Exception as exc:
            log.warning("SSD weights unavailable (%s); using classical detector", exc)
    if proto.exists() and weights.exists() and weights.stat().st_size > 1_000_000:
        return proto, weights
    return None


def _fetch(url: str, dest: Path, timeout: float) -> None:
    log.info("Downloading %s", dest.name)
    with urlopen(url, timeout=timeout) as src, dest.open("wb") as out:
        while True:
            chunk = src.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
