import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

load_dotenv()

from routers import auth, api, mcp  # noqa: E402
from services import database, debate  # noqa: E402

app = FastAPI(title="众声 Voices", version="2.0.0")

# CORS for MCP endpoint (Second Me validation + OpenClaw agents)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_request_body(request, call_next):
    """Reject request bodies larger than 1MB to prevent memory abuse."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1_048_576:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "request body too large"}, status_code=413)
    return await call_next(request)


app.include_router(auth.router)
app.include_router(api.router)
app.include_router(mcp.router)


@app.on_event("startup")
async def startup():
    database.init_db()
    debate._load_debates()
    debate._load_plaza()

# Serve static assets
static_dir = Path(__file__).parent / "static"
app.mount("/sfx", StaticFiles(directory=static_dir / "sfx"), name="sfx")
app.mount("/img", StaticFiles(directory=static_dir / "img"), name="img")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    return FileResponse(static_dir / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.2.0"}


@app.get("/.well-known/mcp")
async def mcp_discovery():
    """MCP Server Discovery endpoint — lets AI agents auto-discover our tools."""
    return {
        "name": "zhongsheng-voices",
        "description": "Analyze hidden consensus in Zhihu discussions. AI reads hundreds of answers, extracts opposing viewpoints, stages a simulated courtroom debate, and reveals what people actually agree on.",
        "description_zh": "分析知乎热门讨论中的隐藏共识。AI 读完高赞回答，提炼对立观点，在模拟法庭中辩论，揭示争论背后大家其实都同意的东西。",
        "url": "https://zhongsheng.ai-builders.space/mcp",
        "version": "1.0.0",
        "protocol_version": "2024-11-05",
        "transport": "http",
        "capabilities": {"tools": True},
        "authentication": {"type": "none"},
        "tools_summary": [
            "zhongsheng_search — Search Zhihu topics by keyword",
            "zhongsheng_hotlist — Get trending Zhihu topics",
            "zhongsheng_list_debates — Browse completed AI debates",
            "zhongsheng_get_debate — View debate details with consensus analysis",
            "zhongsheng_comment — Post a comment on a debate"
        ],
        "homepage": "https://zhongsheng.ai-builders.space",
        "source": "https://github.com/danielzheng1986726/zhongsheng"
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
