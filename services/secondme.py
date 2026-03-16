"""Second Me API client — OAuth token exchange, user info, chat, act, memory."""

import os
import json

import httpx

BASE = "https://api.mindverse.com/gate/lab"
CLIENT_ID = os.getenv("SECONDME_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SECONDME_CLIENT_SECRET", "")


async def exchange_code(code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    import logging
    log = logging.getLogger("secondme")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{BASE}/api/oauth/token/code",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        body = r.json()
        log.warning(f"SecondMe token response: {json.dumps(body, ensure_ascii=False)[:500]}")
        if body.get("code") != 0:
            raise ValueError(f"SecondMe token error: {body}")
        data = body.get("data", body)
        # Handle both "access_token" and "accessToken" key formats
        if "access_token" not in data and "accessToken" in data:
            data["access_token"] = data["accessToken"]
        if "refresh_token" not in data and "refreshToken" in data:
            data["refresh_token"] = data["refreshToken"]
        return data


async def refresh_token(rt: str) -> dict:
    """Refresh access token using refresh token."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{BASE}/api/oauth/token/refresh",
            data={
                "grant_type": "refresh_token",
                "refresh_token": rt,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 0:
            raise ValueError(f"SecondMe refresh error: {body}")
        return body["data"]


async def get_user_info(access_token: str) -> dict:
    """Get basic user info (name, avatar, etc.)."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{BASE}/api/secondme/user/info",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 0:
            raise ValueError(f"SecondMe user info error: {body}")
        return body["data"]


async def get_user_shades(access_token: str) -> list:
    """Get user interest tags."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{BASE}/api/secondme/user/shades",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 0:
            return []
        return body.get("data", {}).get("shades", [])


async def chat_stream(access_token: str, message: str, system_prompt: str = ""):
    """Stream chat with user's AI avatar. Yields content chunks."""
    payload = {"message": message}
    if system_prompt:
        payload["systemPrompt"] = system_prompt
    async with httpx.AsyncClient(timeout=60) as c:
        async with c.stream(
            "POST",
            f"{BASE}/api/secondme/chat/stream",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data)
                        content = parsed["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


async def chat_full(access_token: str, message: str, system_prompt: str = "") -> str:
    """Non-streaming chat — collects full response."""
    parts = []
    async for chunk in chat_stream(access_token, message, system_prompt):
        parts.append(chunk)
    return "".join(parts)


async def act_stream(access_token: str, message: str, action_control: str) -> str:
    """Action judgment — returns the full JSON result."""
    payload = {"message": message, "actionControl": action_control}
    parts = []
    async with httpx.AsyncClient(timeout=30) as c:
        async with c.stream(
            "POST",
            f"{BASE}/api/secondme/act/stream",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data)
                        content = parsed["choices"][0]["delta"].get("content", "")
                        if content:
                            parts.append(content)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    return "".join(parts)


async def ingest_memory(access_token: str, topic: str, summary: str) -> dict:
    """Write debate summary to user's agent memory."""
    payload = {
        "channel": {"kind": "debate", "url": "/"},
        "action": "debate_completed",
        "actionLabel": f"参与了「{topic}」的众声法庭辩论",
        "displayText": summary,
        "refs": [
            {
                "objectType": "debate_result",
                "objectId": f"debate_{hash(topic) % 100000}",
                "contentPreview": summary[:200],
            }
        ],
        "importance": 0.7,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{BASE}/api/secondme/agent_memory/ingest",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        return r.json()
