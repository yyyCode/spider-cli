"""DeepSeek search and page-fetch routes for the workbench."""

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from research.client import DeepSeekClient
from research.config import load_config
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


def get_client():
    """Build a client per request so config changes apply without a restart."""

    return DeepSeekClient(load_config())


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
        results = await run_in_threadpool(
            client.search,
            payload.query,
            payload.count,
            payload.need_content,
            payload.ori_question,
            payload.localization,
        )
        return {"results": results}
    except ResearchError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("DeepSeek search failed")
        return JSONResponse(
            {"detail": "搜索服务内部错误，请查看服务端日志。"},
            status_code=500,
        )


@router.post("/api/research/fetch")
async def research_fetch(payload: FetchRequest):
    try:
        client = get_client()
        result = await run_in_threadpool(client.fetch, payload.url)
        return result
    except ResearchError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("DeepSeek fetch failed")
        return JSONResponse(
            {"detail": "抓取服务内部错误，请查看服务端日志。"},
            status_code=500,
        )
