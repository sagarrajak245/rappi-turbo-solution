"""The LLM contract every provider (and the scripted fake) implements.

Providers return a Pydantic-validated object plus a call record, so the graph never sees raw
text and cost/latency are recorded for every call (KB §3.5).
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from app.core.errors import AppError

T = TypeVar("T", bound=BaseModel)


class LlmCallRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    fallback_used: bool = False


class LlmUnavailable(AppError):
    """Every provider failed or returned invalid output after retries."""

    status_code = 503
    code = "llm_unavailable"


class LlmClient(Protocol):
    async def complete_json(
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, LlmCallRecord]: ...
