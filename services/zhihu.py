"""Zhihu API client with file-based caching."""

import os
import json
import hashlib
import time
from pathlib import Path

import httpx

API_BASE = "https://developer.zhihu.com/api/v1/content"
CACHE_DIR = Path(__file__).parent.parent / "zhihu_cache"
CACHE_DIR.mkdir(exist_ok=True)

ACCESS_KEY = os.getenv("ZHIHU_ACCESS_KEY", "").strip()

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


def _auth_headers() -> dict:
    """Generate Zhihu Developer Platform Bearer auth headers."""
    if not ACCESS_KEY:
        raise RuntimeError("ZHIHU_ACCESS_KEY is required")
    return {
        "Authorization": f"Bearer {ACCESS_KEY}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
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


def _normalize_hot_item(item: dict, index: int) -> dict:
    return {
        "title": item.get("Title", ""),
        "heat": "",
        "answer_count": 0,
        "id": item.get("Url", "") or f"hot_{index}",
        "link_url": item.get("Url", ""),
        "thumbnail_url": item.get("ThumbnailUrl", ""),
        "summary": item.get("Summary", ""),
    }


def _normalize_search_item(item: dict) -> dict:
    content_text = item.get("ContentText", "")
    return {
        "title": item.get("Title", ""),
        "answer_count": item.get("CommentCount", 0),
        "content_text": content_text,
        "content": content_text,
        "link_url": item.get("Url", ""),
        "content_type": item.get("ContentType", ""),
        "author_name": item.get("AuthorName", ""),
        "vote_up_count": item.get("VoteUpCount", 0),
    }


async def get_hotlist(top_cnt: int = 50, publish_in_hours: int = 48) -> list:
    """Fetch Zhihu hot list. Cached for 1 hour."""
    cached = _read_cache("hotlist", max_age=3600)
    if cached is not None:
        return cached

    headers = _auth_headers()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{API_BASE}/hot_list",
                headers=headers,
                params={"Limit": min(max(top_cnt, 1), 30)},
            )
            r.raise_for_status()
            body = r.json()
            if body.get("Code") not in (0, None):
                raise RuntimeError(f"Zhihu hotlist error: {body.get('Message', body.get('Code'))}")
            items = body.get("Data", {}).get("Items", [])
            if items:
                items = [_normalize_hot_item(item, i) for i, item in enumerate(items)]
                _write_cache("hotlist", items)
                return items
    except Exception:
        pass

    return FALLBACK_HOTLIST


def _cleanup_search_cache(max_files: int = 100):
    """Remove oldest search cache files if too many exist."""
    search_files = sorted(CACHE_DIR.glob("search_*.json"), key=lambda p: p.stat().st_mtime)
    if len(search_files) > max_files:
        for f in search_files[:len(search_files) - max_files]:
            try:
                f.unlink()
            except Exception:
                pass


async def search(query: str, count: int = 10) -> list:
    """Search Zhihu. Results cached for 24 hours by query hash."""
    qhash = hashlib.sha256(query.encode()).hexdigest()[:16]
    cached = _read_cache(f"search_{qhash}", max_age=86400)  # 24h expiry
    if cached is not None:
        return cached

    budget = _read_cache("_budget") or {"used": 0}
    if budget["used"] >= 900:
        return []

    headers = _auth_headers()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{API_BASE}/zhihu_search",
                headers=headers,
                params={"Query": query, "Count": min(count, 10)},
            )
            r.raise_for_status()
            body = r.json()
            if body.get("Code") not in (0, None):
                raise RuntimeError(f"Zhihu search error: {body.get('Message', body.get('Code'))}")
            items = body.get("Data", {}).get("Items", [])
            items = [_normalize_search_item(item) for item in items]
            _write_cache(f"search_{qhash}", items)
            budget["used"] += 1
            _write_cache("_budget", budget)
            _cleanup_search_cache()
            return items
    except Exception:
        return []


async def get_question_title(url: str) -> str:
    """Extract question title from a Zhihu URL by fetching the page."""
    import re
    from urllib.parse import urlparse
    # Only allow Zhihu domains to prevent SSRF
    try:
        parsed = urlparse(url)
        if parsed.hostname and not parsed.hostname.endswith("zhihu.com"):
            return ""
    except Exception:
        return ""
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
    return {"error": "zhihu write APIs are not available on the current developer platform"}


async def get_circle_posts(ring_id: str = "", page_num: int = 1, page_size: int = 20) -> list:
    """Get posts from a circle."""
    return []


async def react(content_type: str, content_token: str, action_value: int = 1) -> dict:
    """Like/unlike a post or comment. action_value: 1=like, 0=unlike."""
    return {"error": "zhihu write APIs are not available on the current developer platform"}


async def create_comment(content_type: str, content_token: str, content: str) -> dict:
    """Create a comment on a pin or reply to a comment."""
    return {"error": "zhihu write APIs are not available on the current developer platform"}
