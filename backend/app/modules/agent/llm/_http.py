"""Helpers shared by the HTTP providers: schema prompt, JSON parsing, POST with error mapping."""

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import LlmProviderSettings
from app.modules.agent.llm.base import T
from app.modules.agent.llm.errors import InvalidOutput, ProviderError


def with_schema(system: str, schema: type[T]) -> str:
    """JSON mode guarantees JSON, not the shape, so the schema travels in the system prompt."""
    return (
        f"{system}\n\nRespond with a single JSON object matching this JSON Schema:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )


def parse(text: str, schema: type[T]) -> T:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidOutput("Response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise InvalidOutput("Response JSON is not an object")
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise InvalidOutput(f"Response does not match {schema.__name__}") from exc


def cost_usd(cfg: LlmProviderSettings, tokens_in: int, tokens_out: int) -> float:
    return (
        tokens_in * cfg.price_in_per_mtok_usd + tokens_out * cfg.price_out_per_mtok_usd
    ) / 1_000_000


async def post_json(
    http: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
    provider: str,
) -> dict[str, Any]:
    try:
        resp = await http.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider} request failed: {type(exc).__name__}") from None
    if resp.status_code >= 400:
        raise ProviderError(f"{provider} returned HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise InvalidOutput(f"{provider} response body is not JSON") from exc
    if not isinstance(data, dict):
        raise InvalidOutput(f"{provider} response body is not an object")
    return data
