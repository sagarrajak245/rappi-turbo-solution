"""Fan-out of live events to connected SSE clients. In-memory: one process, no replay.

Missed events are not lost: every notification is also a database row (GET /notifications).
A Redis-backed implementation can replace this behind the same Protocol.
"""

import asyncio
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

Event = dict[str, Any]


class Broadcaster(Protocol):
    def subscribe(self) -> "asyncio.Queue[Event]": ...

    def unsubscribe(self, queue: "asyncio.Queue[Event]") -> None: ...

    async def publish(self, event: Event) -> None: ...


class InMemoryBroadcaster:
    def __init__(self, max_queue: int = 100) -> None:
        self._subs: set[asyncio.Queue[Event]] = set()
        self._max = max_queue

    def subscribe(self) -> "asyncio.Queue[Event]":
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max)
        self._subs.add(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[Event]") -> None:
        self._subs.discard(queue)

    async def publish(self, event: Event) -> None:
        for queue in list(self._subs):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # a stuck client must not block the others
                logger.warning("dropping a notification for a slow subscriber")
