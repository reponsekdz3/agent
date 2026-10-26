from __future__ import annotations

import threading
from collections import deque

from nexuscam.types import FramePacket


class FrameBus:
    """Single-producer, multi-consumer latest-frame bus with drop accounting.

    Capture threads never block on slow consumers. Each subscriber keeps a
    bounded deque; overflow drops the oldest frame and increments a counter.
    """

    def __init__(self, depth: int = 2) -> None:
        self._depth = max(1, depth)
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._subs: dict[str, deque[FramePacket]] = {}
        self._drops: dict[str, int] = {}
        self._seq = 0
        self._closed = False

    def subscribe(self, name: str) -> None:
        with self._lock:
            self._subs[name] = deque(maxlen=self._depth)
            self._drops[name] = 0

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            self._subs.pop(name, None)
            self._drops.pop(name, None)

    def publish(self, packet: FramePacket) -> int:
        with self._lock:
            if self._closed:
                return self._seq
            self._seq = packet.seq
            for name, q in self._subs.items():
                if len(q) == q.maxlen:
                    self._drops[name] += 1
                q.append(packet)
            self._cv.notify_all()
            return self._seq

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def get(self, name: str, timeout: float = 1.0) -> FramePacket | None:
        deadline_wait = timeout
        with self._cv:
            q = self._subs.get(name)
            if q is None:
                return None
            if not q:
                self._cv.wait(timeout=deadline_wait)
                q = self._subs.get(name)
                if not q:
                    return None
            pkt = q.pop()
            q.clear()
            drops = self._drops.get(name, 0)
            if drops:
                self._drops[name] = 0
                return FramePacket(
                    seq=pkt.seq,
                    t_ns=pkt.t_ns,
                    bgr=pkt.bgr,
                    transport=pkt.transport,
                    source_id=pkt.source_id,
                    dropped_upstream=drops,
                )
            return pkt

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cv.notify_all()

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed
