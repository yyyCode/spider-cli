"""FastAPI application for the browser frontend."""

import asyncio
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from .service import WebDownloadError, download_video

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = PROJECT_ROOT / "assets"
MAX_CONCURRENT_DOWNLOADS = 2


@asynccontextmanager
async def lifespan(app):
    app.state.download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    yield


app = FastAPI(title="Spider CLI Web", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


class DownloadRequest(BaseModel):
    url: str


def _cleanup(temp_dir):
    shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/download")
async def api_download(payload: DownloadRequest):
    async with app.state.download_semaphore:
        try:
            result = await run_in_threadpool(download_video, payload.url)
        except WebDownloadError as exc:
            return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
        except Exception as exc:  # pragma: no cover - 防御性兜底
            return JSONResponse(
                {"detail": f"服务器内部错误：{exc}"}, status_code=500
            )

    return FileResponse(
        result.path,
        media_type="video/mp4",
        filename=result.filename,
        background=BackgroundTask(_cleanup, result.temp_dir),
    )
