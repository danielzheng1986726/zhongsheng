import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

load_dotenv()

from routers import auth, api  # noqa: E402

app = FastAPI(title="众声 Voices", version="2.0.0")

app.include_router(auth.router)
app.include_router(api.router)

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
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
