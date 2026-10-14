"""Scripted LLM for tests and offline demos: returns queued responses in order.

A response may be a dict (validated against the requested schema) or an Exception to raise,
which lets tests inject invalid output and provider failures deterministically.
"""

from collections import deque
from typing import Any

from pydantic import ValidationError

from app.modules.agent.llm.base import LlmCallRecord, LlmUnavailable, T


class ScriptedLlm:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self._queue: deque[dict[str, Any] | Exception] = deque(responses)
        self.calls: list[tuple[str, str]] = []  # (schema name, user prompt) per call

    async def complete_json(
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, LlmCallRecord]:
        self.calls.append((schema.__name__, user))
        if not self._queue:
            raise LlmUnavailable("ScriptedLlm has no responses left")
        item = self._queue.popleft()
        if isinstance(item, Exception):
            raise item
        try:
            parsed = schema.model_validate(item)
        except ValidationError as exc:
            raise LlmUnavailable("Scripted response does not match the schema") from exc
        return parsed, LlmCallRecord(provider="fake", model="scripted")
