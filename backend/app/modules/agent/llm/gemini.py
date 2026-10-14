"""Gemini generateContent client with a JSON response MIME type (the fallback provider, KB D4).

The API key goes in the `x-goog-api-key` header, never the URL, so it cannot leak into logs.
"""

import time

import httpx

from app.core.config import LlmProviderSettings
from app.modules.agent.llm._http import cost_usd, parse, post_json, with_schema
from app.modules.agent.llm.base import LlmCallRecord, T
from app.modules.agent.llm.errors import InvalidOutput

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient:
    def __init__(
        self,
        cfg: LlmProviderSettings,
        api_key: str,
        http: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.cfg = cfg
        self._api_key = api_key
        self._http = http or httpx.AsyncClient()
        self._timeout = timeout

    async def complete_json(
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, LlmCallRecord]:
        body = {
            "systemInstruction": {"parts": [{"text": with_schema(system, schema)}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        }
        url = GEMINI_URL.format(model=self.cfg.model)
        headers = {"x-goog-api-key": self._api_key}
        start = time.perf_counter()
        data = await post_json(self._http, url, headers, body, self._timeout, "gemini")
        latency_ms = int((time.perf_counter() - start) * 1000)
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidOutput("gemini response has no candidate text") from exc
        parsed = parse(text, schema)
        usage = data.get("usageMetadata") or {}
        tin = int(usage.get("promptTokenCount", 0))
        tout = int(usage.get("candidatesTokenCount", 0))
        record = LlmCallRecord(
            provider="gemini",
            model=self.cfg.model,
            tokens_in=tin,
            tokens_out=tout,
            latency_ms=latency_ms,
            cost_usd=cost_usd(self.cfg, tin, tout),
        )
        return parsed, record
