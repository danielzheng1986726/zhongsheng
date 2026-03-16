"""AI Builder Chat API wrapper."""

import os
import json

import httpx

API_BASE = os.getenv("AI_BUILDER_API_BASE", "https://space.ai-builders.com/backend")


def _token():
    return os.getenv("AI_BUILDER_TOKEN", "")


async def chat(
    messages: list[dict],
    model: str = "deepseek",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Non-streaming chat completion. Returns assistant content."""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            f"{API_BASE}/v1/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            headers={"Authorization": f"Bearer {_token()}"},
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


async def chat_json(
    messages: list[dict],
    model: str = "deepseek",
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
    return json.loads(text)
