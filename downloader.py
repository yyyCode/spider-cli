from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import requests

from config import AppConfig
from rate_limiter import RateLimiter

EXPIRED_STATUS = {403, 410}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LinkExpiredError(Exception):
    """直链已过期，需要回到页面重新嗅探。"""


class _RetryableError(Exception):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 8.0
    jitter: float = 0.3

    def delay_for(self, attempt: int, rng: random.Random) -> float:
        base = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return base * rng.uniform(1 - self.jitter, 1 + self.jitter)


@dataclass
class DownloadResult:
    ok: bool
    path: str
    bytes_written: int = 0
    resumed: bool = False
    error: str | None = None


class VideoDownloader:
    def __init__(
        self,
        headers: Mapping[str, str],
        limiter: RateLimiter,
        config: AppConfig,
        *,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        http: requests.Session | None = None,
    ):
        self.headers = dict(headers)
        self.limiter = limiter
        self.chunk_size = config.chunk_size
        self.cooldown_seconds = config.cooldown_seconds
        self.retry_policy = retry_policy or RetryPolicy(
            attempts=config.max_retries,
            base_delay=config.backoff_base,
            max_delay=config.backoff_max,
        )
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._http = http or requests.Session()

    def download(self, url: str, filepath: str) -> DownloadResult:
        partial = Path(filepath + ".part")
        last_error = ""
        for attempt in range(1, self.retry_policy.attempts + 1):
            try:
                return self._download_attempt(url, filepath, partial)
            except LinkExpiredError:
                raise
            except _RetryableError as exc:
                last_error = str(exc)
                if attempt >= self.retry_policy.attempts:
                    break
                self._sleep(self.retry_policy.delay_for(attempt, self._rng))
            except (OSError, requests.RequestException) as exc:
                return DownloadResult(
                    False,
                    filepath,
                    self._partial_size(partial),
                    partial.exists(),
                    f"下载失败: {exc}",
                )
        return DownloadResult(
            False,
            filepath,
            self._partial_size(partial),
            partial.exists(),
            f"重试 {self.retry_policy.attempts} 次后仍失败: {last_error}",
        )

    @staticmethod
    def _partial_size(partial: Path) -> int:
        try:
            return partial.stat().st_size
        except OSError:
            return 0

    def _download_attempt(
        self,
        url: str,
        filepath: str,
        partial: Path,
    ) -> DownloadResult:
        resume_from = self._partial_size(partial)
        headers = dict(self.headers)
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"

        try:
            response = self._http.get(
                url,
                headers=headers,
                stream=True,
                timeout=(10, 60),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise _RetryableError(f"请求失败: {exc}") from exc

        try:
            status = response.status_code
            if status in EXPIRED_STATUS:
                raise LinkExpiredError(f"直链已过期: HTTP {status}")
            if status == 416:
                partial.unlink(missing_ok=True)
                raise _RetryableError("HTTP 416，从头重新下载")
            if status == 429:
                self.limiter.block_for(self.cooldown_seconds)
                raise _RetryableError("HTTP 429，请求过于频繁")
            if status in RETRYABLE_STATUS:
                raise _RetryableError(f"HTTP {status}")
            if status not in (200, 206):
                return DownloadResult(
                    False,
                    filepath,
                    resume_from,
                    resume_from > 0,
                    f"HTTP {status}",
                )

            append = status == 206 and resume_from > 0
            total = self._total_size(response, append)
            mode = "ab" if append else "wb"
            if not append:
                resume_from = 0

            try:
                with open(partial, mode) as handle:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if chunk:
                            handle.write(chunk)
            except requests.RequestException as exc:
                raise _RetryableError(f"下载中断: {exc}") from exc

            final_size = partial.stat().st_size
            if total is not None and final_size != total:
                partial.unlink(missing_ok=True)
                raise _RetryableError(
                    f"文件大小不一致: 实际 {final_size} / 期望 {total}"
                )

            os.replace(partial, filepath)
            return DownloadResult(True, filepath, final_size, append)
        finally:
            response.close()

    @staticmethod
    def _total_size(response, append: bool) -> int | None:
        if append:
            content_range = response.headers.get("Content-Range", "")
            if "/" in content_range:
                total = content_range.rsplit("/", 1)[1].strip()
                if total.isdigit():
                    return int(total)
            return None
        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit():
            return int(content_length)
        return None
