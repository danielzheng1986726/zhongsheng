"""Zhihu API client with file-based caching.

Signing: HMAC-SHA256 over 'app_key:{ak}|ts:{ts}|logid:{logid}|extra_info:' → Base64.
Headers: X-App-Key, X-Timestamp, X-Log-Id, X-Sign, X-Extra-Info.
"""

import os
import json
import hashlib
import hmac
import time
import base64
import uuid
from pathlib import Path

import httpx

API_BASE = "https://openapi.zhihu.com"
CACHE_DIR = Path(__file__).parent.parent / "zhihu_cache"
CACHE_DIR.mkdir(exist_ok=True)

AK = os.getenv("ZHIHU_AK", "")
SK = os.getenv("ZHIHU_SK", "")

# Hackathon circles
CIRCLE_IDS = ["2001009660925334090", "2015023739549529606"]
CIRCLE_ID = os.getenv("ZHIHU_CIRCLE_ID", CIRCLE_IDS[0])

# Fallback hot topics when API is unavailable
FALLBACK_HOTLIST = [
    {"title": "年轻人到底该不该躺平？", "heat": "1.2万", "answer_count": 354, "id": "tangping"},
    {"title": "AI 会取代程序员吗？", "heat": "8923", "answer_count": 276, "id": "ai-replace"},
    {"title": "相亲到底靠不靠谱？", "heat": "7654", "answer_count": 198, "id": "xiangqin"},
    {"title": "一线城市还值得待吗？", "heat": "6543", "answer_count": 312, "id": "yixian"},
    {"title": "考研还是直接工作？", "heat": "5432", "answer_count": 245, "id": "kaoyan"},
    {"title": "父母催婚该怎么应对？", "heat": "4321", "answer_count": 189, "id": "cuihun"},
    {"title": "35 岁危机是真的吗？", "heat": "9876", "answer_count": 421, "id": "35weiji"},
    {"title": "远程办公是未来趋势吗？", "heat": "3456", "answer_count": 167, "id": "remote"},
]


def _sign_headers() -> dict:
    """Generate auth headers using Zhihu HMAC-SHA256 + Base64 signing."""
    ts = str(int(time.time()))
    log_id = f"zs_{uuid.uuid4().hex[:16]}"
    sign_str = f"app_key:{AK}|ts:{ts}|logid:{log_id}|extra_info:"
    signature = base64.b64encode(
        hmac.new(SK.encode(), sign_str.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "X-App-Key": AK,
        "X-Timestamp": ts,
        "X-Log-Id": log_id,
        "X-Sign": signature,
        "X-Extra-Info": "",
    }


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str, max_age: int = 0) -> dict | None:
    """Read from file cache. max_age=0 means no expiry."""
    p = _cache_path(key)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    if max_age > 0:
        if time.time() - data.get("_cached_at", 0) > max_age:
            return None
    return data.get("payload")


def _write_cache(key: str, payload):
    p = _cache_path(key)
    p.write_text(json.dumps({"_cached_at": time.time(), "payload": payload}, ensure_ascii=False))


async def get_hotlist(top_cnt: int = 50, publish_in_hours: int = 48) -> list:
    """Fetch Zhihu hot list. Cached for 1 hour."""
    cached = _read_cache("hotlist", max_age=3600)
    if cached is not None:
        return cached

    if not AK or not SK:
        return FALLBACK_HOTLIST

    try:
        headers = _sign_headers()
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{API_BASE}/openapi/billboard/list",
                headers=headers,
                params={"top_cnt": top_cnt, "publish_in_hours": publish_in_hours},
            )
            r.raise_for_status()
            body = r.json()
            items = body.get("data", {}).get("list", [])
            if items:
                _write_cache("hotlist", items)
                return items
    except Exception:
        pass

    return FALLBACK_HOTLIST


async def search(query: str, count: int = 10) -> list:
    """Search Zhihu. Results cached permanently by query hash."""
    qhash = hashlib.sha256(query.encode()).hexdigest()[:16]
    cached = _read_cache(f"search_{qhash}")
    if cached is not None:
        return cached

    budget = _read_cache("_budget") or {"used": 0}
    if budget["used"] >= 900:
        return []

    if not AK or not SK:
        return []

    try:
        headers = _sign_headers()
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{API_BASE}/openapi/search/global",
                headers=headers,
                params={"query": query, "count": min(count, 20)},
            )
            r.raise_for_status()
            body = r.json()
            items = body.get("data", {}).get("items", [])
            _write_cache(f"search_{qhash}", items)
            budget["used"] += 1
            _write_cache("_budget", budget)
            return items
    except Exception:
        return []


async def get_question_title(url: str) -> str:
    """Extract question title from a Zhihu URL by fetching the page."""
    import re
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            # Try <title> tag first
            m = re.search(r"<title[^>]*>(.+?)</title>", r.text, re.DOTALL)
            if m:
                title = m.group(1).strip()
                # Clean up common suffixes like " - 知乎" or " - xxx的文章"
                title = re.sub(r'\s*[-–—]\s*知乎$', '', title)
                title = re.sub(r'\s*[-–—]\s*\S+的(文章|回答).*$', '', title)
                if title and title != '知乎':
                    return title
    except Exception:
        pass
    return ""


# ============ Zhihu Circle (圈子) API ============


async def publish_pin(content: str, title: str = "") -> dict:
    """Publish a pin (想法) to the hackathon circle."""
    if not AK or not SK:
        return {"error": "no credentials"}
    headers = _sign_headers()
    headers["Content-Type"] = "application/json"
    payload = {
        "content": content,
        "ring_id": CIRCLE_ID,
    }
    if title:
        payload["title"] = title
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{API_BASE}/openapi/publish/pin", headers=headers, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


async def get_circle_posts(ring_id: str = "", page_num: int = 1, page_size: int = 20) -> list:
    """Get posts from a circle."""
    rid = ring_id or CIRCLE_ID
    if not AK or not SK:
        return []
    headers = _sign_headers()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{API_BASE}/openapi/ring/detail",
                headers=headers,
                params={"ring_id": rid, "page_num": page_num, "page_size": page_size},
            )
            r.raise_for_status()
            body = r.json()
            return body.get("data", {}).get("contents", [])
    except Exception:
        return []


async def react(content_type: str, content_token: str, action_value: int = 1) -> dict:
    """Like/unlike a post or comment. action_value: 1=like, 0=unlike."""
    if not AK or not SK:
        return {"error": "no credentials"}
    headers = _sign_headers()
    headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{API_BASE}/openapi/reaction",
                headers=headers,
                json={
                    "content_token": content_token,
                    "content_type": content_type,
                    "action_type": "like",
                    "action_value": action_value,
                },
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


async def create_comment(content_type: str, content_token: str, content: str) -> dict:
    """Create a comment on a pin or reply to a comment."""
    if not AK or not SK:
        return {"error": "no credentials"}
    headers = _sign_headers()
    headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{API_BASE}/openapi/comment/create",
                headers=headers,
                json={
                    "content_token": content_token,
                    "content_type": content_type,
                    "content": content,
                },
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}
