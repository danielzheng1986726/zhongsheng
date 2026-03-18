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

    Body: {"text": "...", "nickname": "匿名旁听", "source": "human"|"agent"}
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
        "source": body.get("source", "human"),
        "debate_topic": entry.get("topic", ""),
        "debate_id": debate_id,
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


@router.get("/plaza")
async def plaza():
    """Aggregated activity feed — recent comments across all debates + free comments, newest first."""
    feed = []
    for d in debate.completed_debates:
        topic = d.get("topic", "")
        did = d.get("id", "")
        for c in d.get("comments", []):
            feed.append({**c, "debate_topic": topic, "debate_id": did})
    for r in debate.auditorium_reactions:
        feed.append({
            "text": r.get("reaction", ""),
            "nickname": r.get("user_name", "AI 分身"),
            "source": "agent",
            "debate_topic": r.get("topic", ""),
            "debate_id": "",
            "ts": r.get("ts", 0),
        })
    for c in debate.plaza_comments:
        feed.append(c)
    feed.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return {"feed": feed[:50], "total": len(feed)}


@router.get("/unified-feed")
async def unified_feed():
    """Merged feed: hotlist topics + completed debates + plaza comments, interleaved."""
    HEAVY = {"script", "chars", "consensus_items"}

    # 1) Hotlist topics
    hotlist_items = await zhihu.get_hotlist()

    # 2) Completed debates (lightweight)
    debates_list = [
        {**{k: v for k, v in d.items() if k not in HEAVY}, "feed_type": "debate"}
        for d in reversed(debate.completed_debates[-20:])
    ]

    # 3) Plaza comments (from debates + free)
    comments = []
    for d in debate.completed_debates:
        for c in d.get("comments", []):
            comments.append({**c, "debate_topic": d.get("topic", ""), "debate_id": d.get("id", ""), "feed_type": "comment"})
    for r in debate.auditorium_reactions:
        comments.append({
            "text": r.get("reaction", ""), "nickname": r.get("user_name", "AI 分身"),
            "source": "agent", "debate_topic": r.get("topic", ""), "debate_id": "",
            "feed_type": "comment", "ts": r.get("ts", 0),
        })
    for c in debate.plaza_comments:
        comments.append({**c, "feed_type": "comment"})
    comments.sort(key=lambda x: x.get("ts", 0), reverse=True)

    # 4) Interleave: debates first, then hotlist topics with comments inserted every 3-4 items
    feed = []
    comment_idx = 0
    # Lead with completed debates (most engaging)
    for d in debates_list[:5]:
        feed.append(d)
        if comment_idx < len(comments):
            feed.append(comments[comment_idx])
            comment_idx += 1

    # Then hotlist topics interleaved with remaining comments
    for i, item in enumerate(hotlist_items):
        info = item.get("interaction_info", {})
        hs = item.get("heat_score")
        heat_str = ""
        if hs:
            heat_str = f"{hs/10000:.1f}万" if hs > 10000 else str(hs)
        else:
            heat_str = item.get("heat", "")

        feed.append({
            "feed_type": "topic",
            "title": item.get("title") or item.get("question", ""),
            "heat": heat_str,
            "answer_count": info.get("comment_count") or item.get("answer_count", ""),
            "answers": item.get("answers", []),
            "idx": i,
        })
        # Insert a comment after every 3 topics
        if (i + 1) % 3 == 0 and comment_idx < len(comments):
            feed.append(comments[comment_idx])
            comment_idx += 1

    # Append remaining comments at the end
    while comment_idx < len(comments) and comment_idx < 30:
        feed.append(comments[comment_idx])
        comment_idx += 1

    return {"feed": feed, "debates_count": len(debates_list), "hotlist_count": len(hotlist_items)}


@router.post("/plaza/free-comment")
async def plaza_free_comment(request: Request):
    """Post a free comment to the plaza (not tied to any debate).

    Body: {"text": "...", "nickname": "匿名旁听"}
    """
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return {"error": "text is required"}

    comment = {
        "text": text[:200],
        "nickname": body.get("nickname", "匿名旁听")[:20],
        "source": body.get("source", "human"),
        "debate_topic": "",
        "debate_id": "",
        "ts": time.time(),
    }
    debate.plaza_comments.append(comment)
    debate.save_plaza()
    return {"ok": True, "comment": comment}


@router.post("/plaza/agent-comment")
async def agent_comment(request: Request):
    """Generate a comment using the user's Second Me agent and post it.

    Body: {"debate_id": "..."}
    """
    session = _get_session(request)
    if not session:
        return {"error": "not logged in"}

    body = await request.json()
    debate_id = body.get("debate_id", "")
    entry = debate.find_debate(debate_id)
    if not entry:
        return {"error": "debate not found"}

    topic = entry.get("topic", "")
    golden_quote = entry.get("golden_quote", "")
    access_token = session["access_token"]

    try:
        user_info = await secondme.get_user_info(access_token)
        user_name = user_info.get("name", "AI 分身")

        prompt = (
            f"你在一个叫「众声法庭」的产品里围观了一场关于「{topic}」的辩论。"
            f"辩论金句是：「{golden_quote}」。"
            f"请用你自己的口吻，写一句简短的看法或感想（不超过50字）。"
            f"语气轻松自然，就像在朋友圈评论一样。"
        )
        reply = await secondme.chat_full(access_token, prompt)
        if not reply:
            return {"error": "agent returned empty response"}

        comment = {
            "text": reply.strip()[:200],
            "nickname": user_name,
            "source": "agent",
            "debate_topic": topic,
            "debate_id": debate_id,
            "ts": time.time(),
        }
        if "comments" not in entry:
            entry["comments"] = []
        entry["comments"].append(comment)
        debate.save_debates()

        return {"ok": True, "comment": comment}
    except Exception as e:
        return {"error": str(e)}


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
