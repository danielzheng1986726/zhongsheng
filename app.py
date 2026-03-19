import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

load_dotenv()

from routers import auth, api  # noqa: E402
from services import database, debate  # noqa: E402

app = FastAPI(title="众声 Voices", version="2.0.0")


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
    return {"status": "ok", "version": "2.1.0"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
