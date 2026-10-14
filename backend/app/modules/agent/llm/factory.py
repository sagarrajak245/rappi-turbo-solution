"""Build the LLM client for a role from settings (KB D4: Groq primary, Gemini fallback).

Providers are picked by dict dispatch on `provider`, so adding one is one entry here.
`llm.fault_injection = "primary_down"` swaps the primary for an always-failing client, which
demonstrates the fallback path (R5) without touching the network config.
"""

from collections.abc import Callable

import httpx

from app.core.config import LlmProviderSettings, Settings
from app.modules.agent.llm.base import LlmCallRecord, LlmClient, T
from app.modules.agent.llm.errors import ProviderError
from app.modules.agent.llm.fallback import FallbackLlm
from app.modules.agent.llm.gemini import GeminiClient
from app.modules.agent.llm.groq import GroqClient

_Builder = Callable[[LlmProviderSettings, Settings, httpx.AsyncClient | None], LlmClient]


def _groq(cfg: LlmProviderSettings, s: Settings, http: httpx.AsyncClient | None) -> LlmClient:
    return GroqClient(cfg, s.groq_api_key, http=http, timeout=s.llm.timeout_s)


def _gemini(cfg: LlmProviderSettings, s: Settings, http: httpx.AsyncClient | None) -> LlmClient:
    return GeminiClient(cfg, s.gemini_api_key, http=http, timeout=s.llm.timeout_s)


PROVIDERS: dict[str, _Builder] = {"groq": _groq, "gemini": _gemini}


class _DownClient:
    """Fault injection: a provider that is always unreachable."""

    async def complete_json(
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, LlmCallRecord]:
        raise ProviderError("fault injection: primary provider down")


def _provider(cfg: LlmProviderSettings, s: Settings, http: httpx.AsyncClient | None) -> LlmClient:
    builder = PROVIDERS.get(cfg.provider)
    if builder is None:
        raise ValueError(f"Unknown LLM provider {cfg.provider!r} (known: {sorted(PROVIDERS)})")
    return builder(cfg, s, http)


def build_llm(role: str, settings: Settings, http: httpx.AsyncClient | None = None) -> LlmClient:
    roles = {"decision": settings.llm.decision, "reviewer": settings.llm.reviewer}
    cfg = roles.get(role)
    if cfg is None:
        raise ValueError(f"Unknown LLM role {role!r} (known: {sorted(roles)})")
    primary: LlmClient = (
        _DownClient()
        if settings.llm.fault_injection == "primary_down"
        else _provider(cfg, settings, http)
    )
    fallback = _provider(settings.llm.fallback, settings, http)
    return FallbackLlm(primary, fallback, settings.llm.max_invalid_retries)
