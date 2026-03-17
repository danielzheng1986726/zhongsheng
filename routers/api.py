"""Business API routes — hotlist, debate generation, Second Me participation."""

import asyncio
import json
import logging

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
    """Return completed debates from in-memory history (most recent first)."""
    items = list(reversed(debate.completed_debates[-20:]))
    return {"debates": items, "total": len(debate.completed_debates)}


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


@router.post("/zhihu/publish")
async def publish_to_circle(request: Request):
    """Publish debate result to Zhihu circle as a pin."""
    body = await request.json()
    content = body.get("content", "")
    if not content:
        return {"error": "content is required"}

    result = await zhihu.publish_pin(content)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "result": result}


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

    # Pick top N items that have answers (more context = better debates)
    targets = []
    for item in items[:10]:
        if len(targets) >= count:
            break
        title = item.get("title") or item.get("question", "")
        if title:
            targets.append({"title": title, "answers": item.get("answers", [])})

    async def _run_debate(title: str, answers: list):
        try:
            async for event in debate.generate(title, context_answers=answers):
                pass  # consume the generator — auto-publish happens in debate.py
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
