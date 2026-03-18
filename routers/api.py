"""Business API routes — hotlist, debate generation, Second Me participation."""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from services import zhihu, debate, secondme
from routers.auth import _get_session

log = logging.getLogger("api")

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/hotlist")
async def hotlist():
    """Return Zhihu hot topics."""
    items = await zhihu.get_hotlist()
    return {"items": items}


@router.post("/debate/generate")
async def generate_debate(request: Request):
    """Generate a full courtroom debate via SSE.

    Body: {"topic": "...", "context_answers": [...]}
    Yields SSE events with phase updates, then final 'done' with full payload.
    """
    body = await request.json()
    topic = body.get("topic", "")
    url = body.get("url", "")

    # If a URL was provided, try to resolve the title
    if url and (not topic or topic == '正在解析讨论...'):
        resolved = await zhihu.get_question_title(url)
        if resolved:
            topic = resolved

    if not topic:
        return {"error": "topic is required"}

    context_answers = body.get("context_answers", [])

    session = _get_session(request)
    access_token = session.get("access_token") if session else None

    async def event_stream():
        async for event in debate.generate(
            topic,
            access_token=access_token,
            context_answers=context_answers,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/feed")
async def feed():
    """Return recent debate activity from Zhihu circle posts."""
    # Cache circle posts for 5 minutes to avoid rate limits
    cached = zhihu._read_cache("_feed", max_age=300)
    if cached is not None:
        return {"posts": cached}
    posts = await zhihu.get_circle_posts(page_size=10)
    zhihu._write_cache("_feed", posts)
    return {"posts": posts}


@router.get("/theater")
async def theater():
    """Return completed debates from in-memory history (most recent first).
    Strips heavy fields (script/chars) to keep the response lightweight."""
    HEAVY = {"script", "chars", "consensus_items"}
    items = [
        {k: v for k, v in d.items() if k not in HEAVY}
        for d in reversed(debate.completed_debates[-20:])
    ]
    return {"debates": items, "total": len(debate.completed_debates)}


@router.get("/auditorium")
async def auditorium():
    """Return Second Me agent reactions from the auditorium (most recent first)."""
    items = list(reversed(debate.auditorium_reactions[-50:]))
    return {"reactions": items, "total": len(debate.auditorium_reactions)}


@router.get("/debate/{debate_id}")
async def get_debate(debate_id: str):
    """Return a single debate's data (likes, comments, etc.)."""
    entry = debate.find_debate(debate_id)
    if not entry:
        return {"error": "debate not found"}
    return {
        "ok": True,
        "id": entry.get("id"),
        "likes": entry.get("likes", 0),
        "comments": entry.get("comments", []),
    }


@router.get("/debate/{debate_id}/replay")
async def replay_debate(debate_id: str):
    """Return full replay data (script, chars, consensus) for a completed debate."""
    # Try in-memory first (has script/chars if still loaded)
    entry = debate.find_debate(debate_id)
    if entry and entry.get("script"):
        return {
            "ok": True,
            "debate_id": debate_id,
            "topic": entry.get("topic", ""),
            "script": entry["script"],
            "chars": entry.get("chars", {}),
            "consensus_items": entry.get("consensus_items", []),
            "golden_quote": entry.get("golden_quote", ""),
            "warmth_message": entry.get("warmth_message", ""),
            "likes": entry.get("likes", 0),
            "comments": entry.get("comments", []),
        }
    # Fall back to disk
    replay = debate.load_replay(debate_id)
    if replay:
        likes = entry.get("likes", 0) if entry else 0
        comments = entry.get("comments", []) if entry else []
        return {
            "ok": True,
            **replay,
            "likes": likes,
            "comments": comments,
        }
    return {"error": "replay not found"}


@router.post("/debate/{debate_id}/like")
async def like_debate(debate_id: str):
    """Increment like count for a debate. Syncs to Zhihu circle if pin_token exists."""
    entry = debate.find_debate(debate_id)
    if not entry:
        return {"error": "debate not found"}

    entry["likes"] = entry.get("likes", 0) + 1
    debate.save_debates()

    pin_token = entry.get("pin_token")
    if pin_token:
        asyncio.create_task(_sync_like_to_zhihu(pin_token))

    return {"ok": True, "likes": entry["likes"]}


@router.post("/debate/{debate_id}/comment")
async def comment_debate(debate_id: str, request: Request):
    """Add a comment to a debate. Syncs to Zhihu circle if pin_token exists.

    Body: {"text": "...", "nickname": "匿名旁听"}
    """
    entry = debate.find_debate(debate_id)
    if not entry:
        return {"error": "debate not found"}

    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return {"error": "text is required"}

    comment = {
        "text": text[:200],
        "nickname": body.get("nickname", "匿名旁听")[:20],
        "ts": time.time(),
    }
    if "comments" not in entry:
        entry["comments"] = []
    entry["comments"].append(comment)
    debate.save_debates()

    pin_token = entry.get("pin_token")
    if pin_token:
        asyncio.create_task(_sync_comment_to_zhihu(pin_token, text[:200]))

    return {"ok": True, "comment": comment, "total_comments": len(entry["comments"])}


async def _sync_like_to_zhihu(pin_token: str):
    try:
        await zhihu.react("pin", pin_token, action_value=1)
    except Exception as e:
        log.warning("Zhihu like sync failed: %s", e)


async def _sync_comment_to_zhihu(pin_token: str, text: str):
    try:
        await zhihu.create_comment("pin", pin_token, text)
    except Exception as e:
        log.warning("Zhihu comment sync failed: %s", e)


@router.post("/secondme/memory")
async def write_memory(request: Request):
    """Write debate result to user's Second Me agent memory."""
    session = _get_session(request)
    if not session:
        return {"error": "not logged in"}

    body = await request.json()
    topic = body.get("topic", "")
    summary = body.get("summary", "")
    if not topic or not summary:
        return {"error": "topic and summary are required"}

    try:
        result = await secondme.ingest_memory(
            session["access_token"], topic, summary,
        )
        return {"ok": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


@router.post("/admin/seed")
async def seed_debates(request: Request):
    """Pre-generate debates for top hotlist items to fill the theater feed.

    Body: {"count": 3} (optional, defaults to 3)
    Fires debates in background and returns immediately.
    """
    body = await request.json() if request.headers.get("content-type") else {}
    count = min(body.get("count", 3), 5)

    items = await zhihu.get_hotlist()
    if not items:
        return {"error": "hotlist empty"}

    # Pick top N items, skipping topics already in theater
    existing = {d["topic"] for d in debate.completed_debates}
    targets = []
    for item in items[:20]:
        if len(targets) >= count:
            break
        title = item.get("title") or item.get("question", "")
        if title and title not in existing:
            targets.append({"title": title, "answers": item.get("answers", [])})
            existing.add(title)

    async def _run_debate(title: str, answers: list):
        try:
            async for event in debate.generate(title, context_answers=answers, auto_publish=True):
                pass  # consume the generator — publish to circle only for seed
            log.info("Seed debate done: %s", title[:30])
        except Exception as e:
            log.warning("Seed debate failed for %s: %s", title[:30], e)

    # Fire all debates in background (don't block the response)
    for t in targets:
        asyncio.create_task(_run_debate(t["title"], t["answers"][:5]))

    return {
        "ok": True,
        "seeding": [t["title"][:40] for t in targets],
        "message": f"Generating {len(targets)} debates in background",
    }
