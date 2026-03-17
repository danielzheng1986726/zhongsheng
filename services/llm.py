"""AI Builder Chat API wrapper with MiniMax support."""

import os
import json
import logging
import re

import httpx

log = logging.getLogger("llm")

AI_BUILDER_BASE = os.getenv("AI_BUILDER_API_BASE", "https://space.ai-builders.com/backend")
MINIMAX_BASE = os.getenv("MINIMAX_API_BASE", "https://api.minimax.io")
MINIMAX_KEY = os.getenv("MINIMAX_API_KEY", "")

# MiniMax models use a different base URL and API key
MINIMAX_MODELS = {"MiniMax-M2.5", "MiniMax-M2.5-highspeed", "MiniMax-M2.1", "MiniMax-M2.1-highspeed", "MiniMax-M2"}

# gpt-5 requires max_tokens >= 1000 on AI Builder platform
GPT5_MIN_TOKENS = 1000


def _token():
    return os.getenv("AI_BUILDER_TOKEN", "")


def _resolve_endpoint(model: str) -> tuple[str, str]:
    """Return (base_url, api_key) for the given model."""
    if model in MINIMAX_MODELS and MINIMAX_KEY:
        return MINIMAX_BASE, MINIMAX_KEY
    return AI_BUILDER_BASE, _token()


async def chat(
    messages: list[dict],
    model: str = "grok-4-fast",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Non-streaming chat completion. Returns assistant content."""
    # gpt-5 needs max_tokens >= 1000 or returns empty content
    if model.startswith("gpt-") and max_tokens < GPT5_MIN_TOKENS:
        max_tokens = GPT5_MIN_TOKENS

    base_url, api_key = _resolve_endpoint(model)

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        if not content or not content.strip():
            raise ValueError(f"Model {model} returned empty content")
        # Strip <think>...</think> reasoning blocks (MiniMax-M2.5 etc.)
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
        if not content.strip():
            raise ValueError(f"Model {model} returned only think tags, no content")
        return content


async def chat_json(
    messages: list[dict],
    model: str = "grok-4-fast",
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict | list:
    """Chat completion expecting JSON output. Parses and returns."""
    raw = await chat(messages, model, temperature, max_tokens)
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        first_nl = text.index("\n")
        last_fence = text.rfind("```")
        text = text[first_nl + 1 : last_fence].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract JSON object/array from surrounding text
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise
