"""MCP (Model Context Protocol) endpoint for Second Me integration.

Exposes zhongsheng tools via JSON-RPC over HTTP so that Second Me agents
(OpenClaw) can search topics, view debates, and post comments on behalf of users.
"""

import json
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services import zhihu, debate, database

log = logging.getLogger("mcp")

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ── Tool definitions ────────────────────────────────────────────

TOOLS = [
    {
        "name": "zhongsheng_search",
        "description": "搜索知乎话题，返回相关讨论标题和回答数。用户说'搜一下XX'、'有什么关于XX的讨论'时使用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如'躺平'、'买房'、'考研'"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "zhongsheng_hotlist",
        "description": "获取当前知乎热榜话题列表。用户说'现在什么话题热门'、'看看热榜'时使用。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "zhongsheng_get_debate",
        "description": "查看一场已完成的模拟法庭辩论的详情，包括共识分析和金句。用户说'看看那个辩论'、'辩论结果是什么'时使用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "debate_id": {
                    "type": "string",
                    "description": "辩论ID"
                }
            },
            "required": ["debate_id"]
        }
    },
    {
        "name": "zhongsheng_list_debates",
        "description": "列出众声平台上已完成的所有辩论话题。用户说'有哪些辩论'、'看看都讨论了什么'时使用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认10",
                    "default": 10
                }
            }
        }
    },
    {
        "name": "zhongsheng_comment",
        "description": "对一场辩论发表评论。用户说'我想评论'、'发表看法'时使用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "debate_id": {
                    "type": "string",
                    "description": "辩论ID"
                },
                "text": {
                    "type": "string",
                    "description": "评论内容"
                },
                "nickname": {
                    "type": "string",
                    "description": "评论者昵称"
                }
            },
            "required": ["debate_id", "text"]
        }
    }
]


# ── Tool handlers ───────────────────────────────────────────────

async def _handle_search(args: dict) -> str:
    q = args.get("query", "").strip()
    if not q:
        return json.dumps({"error": "请提供搜索关键词"}, ensure_ascii=False)
    items = await zhihu.search(q, count=6)
    results = []
    for item in items:
        title = item.get("title", "")
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"\s*[-–—]\s*知乎\s*$", "", title)
        if title:
            results.append({
                "title": title,
                "answer_count": item.get("answer_count", 0),
            })
    return json.dumps({
        "results": results,
        "tip": f"找到 {len(results)} 个相关话题。可以去 zhongsheng.ai-builders.space 观看 AI 模拟法庭辩论。"
    }, ensure_ascii=False)


async def _handle_hotlist(args: dict) -> str:
    items = await zhihu.get_hotlist()
    top = items[:10] if items else []
    results = [
        {"rank": i + 1, "title": t.get("target", {}).get("title", t.get("title", "")),
         "heat": t.get("detail_text", "")}
        for i, t in enumerate(top)
    ]
    return json.dumps({
        "hotlist": results,
        "tip": "这些是当前知乎热榜话题。去 zhongsheng.ai-builders.space 选一个，AI 会开庭辩论。"
    }, ensure_ascii=False)


async def _handle_get_debate(args: dict) -> str:
    debate_id = args.get("debate_id", "")
    if not debate_id:
        return json.dumps({"error": "请提供辩论ID"}, ensure_ascii=False)
    entry = debate.find_debate(debate_id)
    if not entry:
        replay = debate.load_replay(debate_id)
        if not replay:
            return json.dumps({"error": "未找到该辩论"}, ensure_ascii=False)
        entry = replay
    result = {
        "topic": entry.get("topic", ""),
        "golden_quote": entry.get("golden_quote", ""),
        "warmth_message": entry.get("warmth_message", ""),
        "likes": entry.get("likes", 0),
        "comment_count": len(entry.get("comments", [])),
    }
    consensus = entry.get("consensus_items", [])
    if consensus:
        result["consensus"] = [
            {"label": c.get("label", ""), "pct": c.get("pct", ""), "detail": c.get("detail", "")}
            for c in consensus[:5]
        ]
    return json.dumps(result, ensure_ascii=False)


async def _handle_list_debates(args: dict) -> str:
    limit = min(args.get("limit", 10), 20)
    items = list(reversed(debate.completed_debates[-limit:]))
    results = []
    for d in items:
        results.append({
            "id": d.get("id", ""),
            "topic": d.get("topic", ""),
            "golden_quote": d.get("golden_quote", ""),
            "likes": d.get("likes", 0),
            "comment_count": len(d.get("comments", [])),
        })
    return json.dumps({
        "debates": results,
        "total": len(debate.completed_debates),
        "tip": "去 zhongsheng.ai-builders.space 观看完整辩论回放。"
    }, ensure_ascii=False)


async def _handle_comment(args: dict) -> str:
    debate_id = args.get("debate_id", "")
    text = (args.get("text", "") or "")[:200]
    nickname = (args.get("nickname", "") or "龙虾用户")[:20]
    if not debate_id or not text:
        return json.dumps({"error": "请提供 debate_id 和评论内容"}, ensure_ascii=False)
    entry = debate.find_debate(debate_id)
    if not entry:
        return json.dumps({"error": "未找到该辩论"}, ensure_ascii=False)
    import time
    comment = {
        "text": text,
        "nickname": nickname,
        "source": "agent",
        "debate_topic": entry.get("topic", ""),
        "debate_id": debate_id,
        "ts": time.time(),
    }
    if "comments" not in entry:
        entry["comments"] = []
    entry["comments"].append(comment)
    try:
        database.add_comment(comment)
        database.sync()
    except Exception:
        pass
    return json.dumps({"ok": True, "message": "评论已发布"}, ensure_ascii=False)


TOOL_HANDLERS = {
    "zhongsheng_search": _handle_search,
    "zhongsheng_hotlist": _handle_hotlist,
    "zhongsheng_get_debate": _handle_get_debate,
    "zhongsheng_list_debates": _handle_list_debates,
    "zhongsheng_comment": _handle_comment,
}


# ── MCP JSON-RPC endpoint ──────────────────────────────────────

@router.post("")
@router.post("/")
async def mcp_endpoint(request: Request):
    """Handle MCP JSON-RPC requests (initialize, tools/list, tools/call)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})

    method = body.get("method", "")
    req_id = body.get("id")
    params = body.get("params", {})

    # ── initialize ──
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "zhongsheng-voices",
                    "version": "1.0.0"
                }
            }
        })

    # ── tools/list ──
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        })

    # ── tools/call ──
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            })
        try:
            result_text = await handler(arguments)
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}]
                }
            })
        except Exception as e:
            log.exception("Tool call failed: %s", tool_name)
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(e)}
            })

    # ── notifications (no response needed) ──
    if method in ("notifications/initialized", "notifications/cancelled"):
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})

    # ── unknown method ──
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    })
