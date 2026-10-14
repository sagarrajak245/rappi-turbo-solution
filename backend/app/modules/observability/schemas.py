from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class LlmUsage(_Frozen):
    provider: str
    model: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    fallback_calls: int


class Metrics(_Frozen):
    runs_by_status: dict[str, int]
    total_runs: int
    llm: list[LlmUsage]
    total_llm_calls: int
    total_cost_usd: float
    avg_cost_per_run: float
    fallback_rate: float  # share of LLM calls served by a fallback provider
