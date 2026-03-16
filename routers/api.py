"""Business API routes — hotlist, debate generation, Second Me participation."""

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from services import zhihu, debate, secondme
from routers.auth import _get_session

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
