"""Orchestrate platform downloads for the web frontend."""

import os
import shutil
import tempfile
import time
from dataclasses import dataclass

from core.spiders import (
    SUPPORTED_PLATFORMS,
    UNSUPPORTED_PLATFORM_MESSAGE,
    create_spider,
)
from core.utils import detect_platform, extract_url_from_text


class WebDownloadError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class DownloadedFile:
    path: str
    filename: str
    temp_dir: str


def _resolve_input(raw_url):
    url = extract_url_from_text((raw_url or "").strip())
    if not url:
        raise WebDownloadError("未识别到有效链接，请粘贴完整的分享口令或 URL", 400)
    platform = detect_platform(url)
    if platform not in SUPPORTED_PLATFORMS:
        raise WebDownloadError(UNSUPPORTED_PLATFORM_MESSAGE, 400)
    return url, platform


def _failure_detail(logs, fallback):
    tail = [line for line in logs[-3:] if line]
    return "；".join(tail) if tail else fallback


def _download_douyin(spider, logs):
    path = spider.run()
    if not path:
        raise WebDownloadError(
            _failure_detail(logs, "抖音解析失败，可能链接失效或触发了风控"), 502
        )
    return path


def _download_xhs(spider, logs):
    media = spider.resolve()
    if media.kind != "video":
        raise WebDownloadError("小红书图集暂不支持，当前仅支持视频", 400)
    path = spider.download_note(media)
    if not path:
        raise WebDownloadError(
            _failure_detail(logs, "小红书视频下载失败"), 502
        )
    return path


def _request_log(logs):
    """记录日志并输出到服务端控制台，便于排查耗时和失败原因。"""
    def log(message):
        logs.append(message)
        print(f"[web] {message}", flush=True)

    return log


def download_video(raw_url):
    """同步执行一次视频下载，文件保存在本次请求的临时目录中。"""
    url, platform = _resolve_input(raw_url)
    temp_dir = tempfile.mkdtemp(prefix="spider-web-")
    logs = []
    log = _request_log(logs)
    started = time.time()

    try:
        spider = create_spider(platform, url, temp_dir, log)
        if platform == "douyin":
            path = _download_douyin(spider, logs)
        else:
            path = _download_xhs(spider, logs)

        if not path or not os.path.isfile(path):
            raise WebDownloadError(
                _failure_detail(logs, "未能获取到视频文件，可能链接失效或内容受限"),
                502,
            )

        log(f"请求完成，总耗时 {time.time() - started:.1f}s")
        return DownloadedFile(
            path=path,
            filename=os.path.basename(path),
            temp_dir=temp_dir,
        )
    except WebDownloadError:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise WebDownloadError(
            _failure_detail(logs, f"下载失败：{exc}"), 502
        ) from exc
