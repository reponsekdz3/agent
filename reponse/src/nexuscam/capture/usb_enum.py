from __future__ import annotations

import logging
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import cv2

log = logging.getLogger(__name__)


@dataclass(slots=True)
class UsbCameraInfo:
    index: int
    name: str
    backend: str
    width: int
    height: int
    is_pc_camera: bool = False
    pnp_names: list[str] = field(default_factory=list)

    @property
    def source_id(self) -> str:
        slug = "".join(ch if ch.isalnum() else "-" for ch in self.name.lower())[:28].strip("-")
        prefix = "pc" if self.is_pc_camera else "usb"
        return f"{prefix}:{self.index}:{slug or 'camera'}"


def windows_pnp_camera_names() -> list[str]:
    if platform.system() != "Windows":
        return []
    script = (
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { "
        "$_.Class -eq 'Camera' -or $_.Class -eq 'Image' -or "
        "$_.FriendlyName -match 'Camera|Webcam|Imaging|USB Video' "
        "} | Select-Object -ExpandProperty FriendlyName"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("PnP camera query failed: %s", exc)
        return []
    names = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _probe(index: int, backend_id: int, backend_name: str) -> UsbCameraInfo | None:
    cap = cv2.VideoCapture(index, backend_id)
    try:
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or frame.shape[1])
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or frame.shape[0])
        return UsbCameraInfo(index=index, name=f"Camera {index}", backend=backend_name, width=w, height=h)
    except Exception:
        return None
    finally:
        cap.release()


def enumerate_usb_cameras(max_index: int = 12) -> list[UsbCameraInfo]:
    """Probe every local UVC / PC webcam index. Windows prefers DirectShow then Media Foundation."""
    backends: list[tuple[int, str]] = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append((cv2.CAP_DSHOW, "dshow"))
    if hasattr(cv2, "CAP_MSMF"):
        backends.append((cv2.CAP_MSMF, "msmf"))
    backends.append((cv2.CAP_ANY, "any"))

    found: dict[int, UsbCameraInfo] = {}
    pnp = windows_pnp_camera_names()

    for backend_id, backend_name in backends:
        jobs = []
        with ThreadPoolExecutor(max_workers=min(6, max_index + 1)) as pool:
            for i in range(max_index + 1):
                if i in found:
                    continue
                jobs.append(pool.submit(_probe, i, backend_id, backend_name))
            for fut in as_completed(jobs):
                info = fut.result()
                if info is not None:
                    found[info.index] = info
        if found and backend_name in {"dshow", "msmf"}:
            break

    ordered = [found[i] for i in sorted(found)]
    for i, cam in enumerate(ordered):
        if i < len(pnp):
            cam.name = pnp[i]
            cam.pnp_names = list(pnp)
        cam.is_pc_camera = i == 0 or any(
            k in cam.name.lower() for k in ("integrated", "built-in", "facetime", "laptop", "pc camera", "hd webcam")
        )
        if cam.is_pc_camera and "usb" in cam.name.lower() and "integrated" not in cam.name.lower():
            cam.is_pc_camera = i == 0
    return ordered
