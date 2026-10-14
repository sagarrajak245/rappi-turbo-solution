"""Groq chat-completions client in JSON-object mode (OpenAI-compatible API).

Plain httpx instead of LangChain: `with_structured_output` fails for gpt-oss on Groq (KB §3.7),
so we ask for a JSON object and validate it with Pydantic ourselves.
"""

import time

import httpx

from app.core.config import LlmProviderSettings
from app.modules.agent.llm._http import cost_usd, parse, post_json, with_schema
from app.modules.agent.llm.base import LlmCallRecord, T
from app.modules.agent.llm.errors import InvalidOutput

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
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
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": with_schema(system, schema)},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        start = time.perf_counter()
        data = await post_json(self._http, GROQ_URL, headers, body, self._timeout, "groq")
        latency_ms = int((time.perf_counter() - start) * 1000)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidOutput("groq response has no message content") from exc
        parsed = parse(content, schema)
        usage = data.get("usage") or {}
        tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        record = LlmCallRecord(
            provider="groq",
            model=self.cfg.model,
            tokens_in=tin,
            tokens_out=tout,
            latency_ms=latency_ms,
            cost_usd=cost_usd(self.cfg, tin, tout),
        )
        return parsed, record
