"""Primary → retry on invalid output → fallback provider → LlmUnavailable (KB §3.3, R3/R5).

Invalid output is retried on the primary (the model may just have slipped); a provider error is
not, because the provider is down or erroring and another try would only add latency.
"""

import logging

from app.modules.agent.llm.base import LlmCallRecord, LlmClient, LlmUnavailable, T
from app.modules.agent.llm.errors import InvalidOutput, ProviderError

logger = logging.getLogger(__name__)


class FallbackLlm:
    def __init__(self, primary: LlmClient, fallback: LlmClient, max_invalid_retries: int) -> None:
        self.primary = primary
        self.fallback = fallback
        self._max_invalid_retries = max_invalid_retries

    async def complete_json(
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, LlmCallRecord]:
        for attempt in range(self._max_invalid_retries + 1):
            try:
                return await self.primary.complete_json(system, user, schema)
            except InvalidOutput as exc:
                logger.warning("primary LLM invalid output (attempt %d): %s", attempt + 1, exc)
            except ProviderError as exc:
                logger.warning("primary LLM provider error: %s", exc)
                break
        try:
            parsed, record = await self.fallback.complete_json(system, user, schema)
        except (InvalidOutput, ProviderError) as exc:
            logger.error("fallback LLM failed: %s", exc)
            raise LlmUnavailable(
                "Both the primary and the fallback LLM failed", {"schema": schema.__name__}
            ) from exc
        return parsed, record.model_copy(update={"fallback_used": True})
