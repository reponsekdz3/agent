from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[Any], Awaitable[None] | None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def on(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    async def emit(self, topic: str, payload: Any) -> None:
        handlers = list(self._subs.get(topic, ()))
        for handler in handlers:
            result = handler(payload)
            if asyncio.iscoroutine(result):
                await result
