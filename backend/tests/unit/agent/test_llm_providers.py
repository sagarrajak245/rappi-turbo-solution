"""Groq/Gemini clients, fallback and factory. All HTTP goes through httpx.MockTransport."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.config import LlmProviderSettings, LlmSettings, Settings
from app.modules.agent.llm.base import LlmUnavailable
from app.modules.agent.llm.errors import InvalidOutput, ProviderError
from app.modules.agent.llm.factory import build_llm
from app.modules.agent.llm.fallback import FallbackLlm
from app.modules.agent.llm.gemini import GeminiClient
from app.modules.agent.llm.groq import GroqClient
from app.modules.agent.schemas import ReviewOut

GROQ_CFG = LlmProviderSettings(
    provider="groq",
    model="openai/gpt-oss-120b",
    price_in_per_mtok_usd=1.0,
    price_out_per_mtok_usd=2.0,
)
GEMINI_CFG = LlmProviderSettings(
    provider="gemini",
    model="gemini-2.5-flash",
    price_in_per_mtok_usd=1.0,
    price_out_per_mtok_usd=4.0,
)

Handler = Callable[[httpx.Request], httpx.Response]


def groq_body(content: str, tin: int = 1000, tout: int = 500) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": tin, "completion_tokens": tout},
    }


def gemini_body(text: str, tin: int = 1000, tout: int = 500) -> dict[str, Any]:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": tin, "candidatesTokenCount": tout},
    }


def client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def sequence(*responses: httpx.Response) -> tuple[httpx.AsyncClient, list[int]]:
    """A client answering with `responses` in order (the last one repeats)."""
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return responses[min(len(calls), len(responses)) - 1]

    return client(handler), calls


def chain(groq_http: httpx.AsyncClient, gem_http: httpx.AsyncClient) -> FallbackLlm:
    return FallbackLlm(
        GroqClient(GROQ_CFG, "k", http=groq_http),
        GeminiClient(GEMINI_CFG, "k", http=gem_http),
        max_invalid_retries=1,
    )


async def test_groq_request_shape_and_cost_record() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=groq_body('{"ok": true, "issues": []}'))

    llm = GroqClient(GROQ_CFG, "gk-test", http=client(handler))
    out, rec = await llm.complete_json("be careful", "check this", ReviewOut)

    assert out == ReviewOut(ok=True)
    req = seen[0]
    assert str(req.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer gk-test"
    body = json.loads(req.content)
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert "be careful" in body["messages"][0]["content"]
    assert "issues" in body["messages"][0]["content"]  # schema appended to the system prompt
    assert body["messages"][1] == {"role": "user", "content": "check this"}
    assert (rec.provider, rec.model, rec.tokens_in, rec.tokens_out) == (
        "groq",
        "openai/gpt-oss-120b",
        1000,
        500,
    )
    assert rec.cost_usd == pytest.approx(1000 * 1.0 / 1e6 + 500 * 2.0 / 1e6)
    assert rec.fallback_used is False


async def test_gemini_request_shape_key_in_header_not_url() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=gemini_body('{"ok": false, "issues": ["x"]}'))

    llm = GeminiClient(GEMINI_CFG, "gm-test", http=client(handler))
    out, rec = await llm.complete_json("sys", "usr", ReviewOut)

    assert out == ReviewOut(ok=False, issues=["x"])
    req = seen[0]
    assert req.url.path == "/v1beta/models/gemini-2.5-flash:generateContent"
    assert "gm-test" not in str(req.url)
    assert req.headers["x-goog-api-key"] == "gm-test"
    body = json.loads(req.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "sys" in body["systemInstruction"]["parts"][0]["text"]
    assert body["contents"][0]["parts"][0]["text"] == "usr"
    assert (rec.provider, rec.tokens_in, rec.tokens_out) == ("gemini", 1000, 500)
    assert rec.cost_usd == pytest.approx(1000 * 1.0 / 1e6 + 500 * 4.0 / 1e6)


@pytest.mark.parametrize("content", ["not json", '{"issues": []}', '["ok"]'])
async def test_invalid_output_is_reported_as_invalid(content: str) -> None:
    http, _ = sequence(httpx.Response(200, json=groq_body(content)))
    with pytest.raises(InvalidOutput):
        await GroqClient(GROQ_CFG, "k", http=http).complete_json("s", "u", ReviewOut)


async def test_malformed_envelope_is_invalid_output() -> None:
    http, _ = sequence(httpx.Response(200, json={"candidates": []}))
    with pytest.raises(InvalidOutput):
        await GeminiClient(GEMINI_CFG, "k", http=http).complete_json("s", "u", ReviewOut)


async def test_http_error_is_provider_error_without_key_in_message() -> None:
    http, _ = sequence(httpx.Response(500, text="boom"))
    with pytest.raises(ProviderError) as exc:
        await GroqClient(GROQ_CFG, "secret-key", http=http).complete_json("s", "u", ReviewOut)
    assert "secret-key" not in str(exc.value)


async def test_timeout_is_provider_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    llm = GeminiClient(GEMINI_CFG, "k", http=client(handler))
    with pytest.raises(ProviderError):
        await llm.complete_json("s", "u", ReviewOut)


async def test_r3_invalid_json_retries_primary_then_falls_back() -> None:
    bad = httpx.Response(200, json=groq_body("nope"))
    groq_http, groq_calls = sequence(bad, bad)
    gem_http, gem_calls = sequence(httpx.Response(200, json=gemini_body('{"ok": true}')))
    out, rec = await chain(groq_http, gem_http).complete_json("s", "u", ReviewOut)
    assert out.ok is True
    assert len(groq_calls) == 2 and len(gem_calls) == 1
    assert rec.provider == "gemini" and rec.fallback_used is True


async def test_r3_retry_on_primary_can_succeed_without_fallback() -> None:
    groq_http, groq_calls = sequence(
        httpx.Response(200, json=groq_body("nope")),
        httpx.Response(200, json=groq_body('{"ok": true}')),
    )
    gem_http, gem_calls = sequence(httpx.Response(500))
    _, rec = await chain(groq_http, gem_http).complete_json("s", "u", ReviewOut)
    assert len(groq_calls) == 2 and not gem_calls
    assert rec.provider == "groq" and rec.fallback_used is False


async def test_r5_groq_down_goes_straight_to_gemini() -> None:
    groq_http, groq_calls = sequence(httpx.Response(503))
    gem_http, _ = sequence(httpx.Response(200, json=gemini_body('{"ok": true}')))
    _, rec = await chain(groq_http, gem_http).complete_json("s", "u", ReviewOut)
    assert len(groq_calls) == 1  # a provider error is not retried on the primary
    assert rec.fallback_used is True


async def test_both_down_raises_llm_unavailable() -> None:
    groq_http, _ = sequence(httpx.Response(500))
    gem_http, _ = sequence(httpx.Response(200, json=gemini_body("garbage")))
    with pytest.raises(LlmUnavailable):
        await chain(groq_http, gem_http).complete_json("s", "u", ReviewOut)


def test_factory_builds_fallback_chain_per_role() -> None:
    s = Settings(groq_api_key="g", gemini_api_key="m")
    for role, model in (("decision", s.llm.decision.model), ("reviewer", s.llm.reviewer.model)):
        llm = build_llm(role, s)
        assert isinstance(llm, FallbackLlm)
        assert isinstance(llm.primary, GroqClient) and llm.primary.cfg.model == model
        assert isinstance(llm.fallback, GeminiClient)


def test_factory_rejects_unknown_provider_and_role() -> None:
    bad = Settings(llm=LlmSettings(decision=LlmProviderSettings(provider="nope", model="m")))
    with pytest.raises(ValueError):
        build_llm("decision", bad)
    with pytest.raises(ValueError):
        build_llm("planner", Settings())


async def test_fault_injection_primary_down_uses_fallback() -> None:
    s = Settings(llm=LlmSettings(fault_injection="primary_down"))
    gem_http, _ = sequence(httpx.Response(200, json=gemini_body('{"ok": true}')))
    llm = build_llm("reviewer", s, http=gem_http)
    _, rec = await llm.complete_json("s", "u", ReviewOut)
    assert rec.provider == "gemini" and rec.fallback_used is True
