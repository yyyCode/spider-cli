"""DeepSeek search and page-fetch routes for the workbench."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from research.client import DeepSeekClient
from research.config import load_config, resolve_config_path
from research.errors import ResearchConfigError, ResearchError

router = APIRouter()
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str
    count: Optional[int] = None
    need_content: Optional[bool] = None
    ori_question: Optional[str] = None
    localization: Optional[str] = None


class FetchRequest(BaseModel):
    url: str


_client_cache = {"key": None, "client": None}


def _client_key():
    """Identify the current config so edits still apply without a restart."""

    path = resolve_config_path()
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = None
    return (
        str(path),
        stamp,
        os.environ.get("DEEPSEEK_API_KEY"),
        os.environ.get("DEEPSEEK_BASE_URL"),
    )


def get_client():
    """Reuse the client and its connection pool until the config changes."""

    key = _client_key()
    if _client_cache["key"] != key:
        _client_cache["client"] = DeepSeekClient(load_config())
        _client_cache["key"] = key
    return _client_cache["client"]


async def _client_call(fn, *args, label):
    """Run a blocking client call and map unexpected failures to a 500."""

    try:
        return await run_in_threadpool(fn, *args)
    except ResearchError:
        raise
    except Exception:
        logger.exception("DeepSeek %s failed", label)
        raise HTTPException(
            status_code=500,
            detail=f"{label}服务内部错误，请查看服务端日志。",
        ) from None


def _error_response(exc):
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@router.get("/research", include_in_schema=False)
async def research_page():
    """Keep old links working; the tools now share the workbench page."""

    return RedirectResponse(url="/#research", status_code=307)


@router.get("/api/research/status")
async def research_status():
    try:
        config = load_config()
    except ResearchConfigError as exc:
        return {"configured": False, "message": exc.message}
    return {
        "configured": True,
        "base_url": config.base_url,
        "default_count": config.default_count,
        "default_need_content": config.default_need_content,
    }


@router.post("/api/research/search")
async def research_search(payload: SearchRequest):
    try:
        client = get_client()
        results = await _client_call(
            client.search,
            payload.query,
            payload.count,
            payload.need_content,
            payload.ori_question,
            payload.localization,
            label="搜索",
        )
        return {"results": results}
    except ResearchError as exc:
        return _error_response(exc)


@router.post("/api/research/fetch")
async def research_fetch(payload: FetchRequest):
    try:
        client = get_client()
        return await _client_call(client.fetch, payload.url, label="抓取")
    except ResearchError as exc:
        return _error_response(exc)
