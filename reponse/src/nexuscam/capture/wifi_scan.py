from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

log = logging.getLogger(__name__)

DEFAULT_PORTS = (8080, 4747, 8081, 8554, 554, 8082, 8888, 8090)
DEFAULT_PATHS = ("/video", "/mjpeg", "/live", "/h264", "/videofeed", "/")
USB_TETHER_HOSTS = ("192.168.43.1", "192.168.42.129", "192.168.137.1", "172.20.10.1")


@dataclass(slots=True)
class WifiEndpoint:
    host: str
    port: int
    url: str
    kind: str  # rtsp | http


def local_ipv4s() -> list[str]:
    ips: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


def _tcp_open(host: str, port: int, timeout: float = 0.18) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _hosts_to_probe(extra_hosts: list[str] | None = None) -> list[str]:
    hosts: list[str] = ["127.0.0.1"]
    hosts.extend(USB_TETHER_HOSTS)
    for ip in local_ipv4s():
        hosts.append(ip)
        try:
            net = IPv4Network(f"{ip}/24", strict=False)
            # nearby first: gateway-ish and self ± 20, then rest of /24 is too large —
            # probe .1-.20 and last octet neighborhood
            me = IPv4Address(ip)
            last = int(me) & 0xFF
            candidates = set(range(1, 21)) | set(range(max(1, last - 12), min(254, last + 13)))
            for oct_ in candidates:
                hosts.append(str((int(net.network_address) & 0xFFFFFF00) + oct_))
        except Exception:
            continue
    if extra_hosts:
        hosts.extend(extra_hosts)
    # unique preserve
    seen: set[str] = set()
    out: list[str] = []
    for h in hosts:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def discover_wifi_cameras(
    ports: list[int] | tuple[int, ...] = DEFAULT_PORTS,
    extra_hosts: list[str] | None = None,
    max_workers: int = 64,
) -> list[WifiEndpoint]:
    hosts = _hosts_to_probe(extra_hosts)
    found: list[WifiEndpoint] = []
    seen_urls: set[str] = set()

    def check(host: str, port: int) -> WifiEndpoint | None:
        if not _tcp_open(host, port):
            return None
        if port in {554, 8554}:
            url = f"rtsp://{host}:{port}/live"
            return WifiEndpoint(host=host, port=port, url=url, kind="rtsp")
        path = DEFAULT_PATHS[0]
        url = f"http://{host}:{port}{path}"
        return WifiEndpoint(host=host, port=port, url=url, kind="http")

    jobs = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for host in hosts:
            for port in ports:
                jobs.append(pool.submit(check, host, port))
        for fut in as_completed(jobs):
            ep = fut.result()
            if ep and ep.url not in seen_urls:
                seen_urls.add(ep.url)
                found.append(ep)
    found.sort(key=lambda e: (e.host, e.port))
    log.info("Wi-Fi camera scan found %d endpoint(s)", len(found))
    return found
