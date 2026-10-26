import random

import pytest
import requests

from config import AppConfig
from downloader import LinkExpiredError, RetryPolicy, VideoDownloader


class FakeResponse:
    def __init__(self, status_code, chunks=(), headers=None):
        self.status_code = status_code
        self._chunks = list(chunks)
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size=8192):
        yield from self._chunks

    def close(self):
        self.closed = True


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, headers=None, stream=True, timeout=None):
        self.requests.append({"url": url, "headers": dict(headers or {})})
        if not self.responses:
            raise AssertionError("没有可用的假响应")
        return self.responses.pop(0)


class RecordingLimiter:
    def __init__(self):
        self.blocks = []

    def block_for(self, seconds):
        self.blocks.append(seconds)


def make_downloader(tmp_path, responses, *, attempts=2, cooldown=30):
    config = AppConfig(
        save_dir=tmp_path,
        max_retries=attempts,
        backoff_base=1.0,
        backoff_max=4.0,
        cooldown_seconds=cooldown,
        chunk_size=8,
    )
    http = FakeHttp(responses)
    limiter = RecordingLimiter()
    slept = []
    downloader = VideoDownloader(
        {"Referer": "https://www.douyin.com/"},
        limiter,
        config,
        retry_policy=RetryPolicy(
            attempts=attempts,
            base_delay=1.0,
            max_delay=4.0,
            jitter=0.0,
        ),
        sleep=slept.append,
        rng=random.Random(0),
        http=http,
    )
    return downloader, http, limiter, slept


def test_fresh_download_writes_file_and_removes_part(tmp_path):
    response = FakeResponse(200, [b"abc", b"def"], {"Content-Length": "6"})
    downloader, http, _, _ = make_downloader(tmp_path, [response])
    target = tmp_path / "video.mp4"

    result = downloader.download("https://cdn/video.mp4", str(target))

    assert result.ok is True
    assert result.bytes_written == 6
    assert result.resumed is False
    assert target.read_bytes() == b"abcdef"
    assert not (tmp_path / "video.mp4.part").exists()
    assert "Range" not in http.requests[0]["headers"]


def test_resume_uses_range_and_appends(tmp_path):
    partial = tmp_path / "video.mp4.part"
    partial.write_bytes(b"abc")
    response = FakeResponse(
        206,
        [b"def"],
        {"Content-Range": "bytes 3-5/6"},
    )
    downloader, http, _, _ = make_downloader(tmp_path, [response])
    target = tmp_path / "video.mp4"

    result = downloader.download("https://cdn/video.mp4", str(target))

    assert result.ok is True
    assert result.resumed is True
    assert result.bytes_written == 6
    assert target.read_bytes() == b"abcdef"
    assert http.requests[0]["headers"]["Range"] == "bytes=3-"


def test_server_ignoring_range_restarts_from_scratch(tmp_path):
    partial = tmp_path / "video.mp4.part"
    partial.write_bytes(b"old")
    response = FakeResponse(200, [b"new"], {"Content-Length": "3"})
    downloader, _, _, _ = make_downloader(tmp_path, [response])
    target = tmp_path / "video.mp4"

    result = downloader.download("https://cdn/video.mp4", str(target))

    assert result.ok is True
    assert result.resumed is False
    assert target.read_bytes() == b"new"


def test_expired_link_raises_and_does_not_retry(tmp_path):
    downloader, http, _, _ = make_downloader(
        tmp_path,
        [FakeResponse(403)],
    )
    with pytest.raises(LinkExpiredError):
        downloader.download("https://cdn/video.mp4", str(tmp_path / "video.mp4"))
    assert len(http.requests) == 1


def test_retryable_5xx_then_success(tmp_path):
    responses = [
        FakeResponse(503),
        FakeResponse(200, [b"ok"], {"Content-Length": "2"}),
    ]
    downloader, http, _, slept = make_downloader(tmp_path, responses)
    target = tmp_path / "video.mp4"

    result = downloader.download("https://cdn/video.mp4", str(target))

    assert result.ok is True
    assert target.read_bytes() == b"ok"
    assert len(http.requests) == 2
    assert slept == [1.0]


def test_429_triggers_cooldown(tmp_path):
    responses = [
        FakeResponse(429),
        FakeResponse(200, [b"ok"], {"Content-Length": "2"}),
    ]
    downloader, _, limiter, _ = make_downloader(tmp_path, responses, cooldown=30)
    target = tmp_path / "video.mp4"

    result = downloader.download("https://cdn/video.mp4", str(target))

    assert result.ok is True
    assert limiter.blocks == [30]


def test_size_mismatch_restarts_once_then_succeeds(tmp_path):
    responses = [
        FakeResponse(200, [b"abc"], {"Content-Length": "6"}),
        FakeResponse(200, [b"abcdef"], {"Content-Length": "6"}),
    ]
    downloader, http, _, slept = make_downloader(tmp_path, responses)
    target = tmp_path / "video.mp4"

    result = downloader.download("https://cdn/video.mp4", str(target))

    assert result.ok is True
    assert target.read_bytes() == b"abcdef"
    assert len(http.requests) == 2
    assert slept == [1.0]


def test_non_retryable_4xx_returns_failure(tmp_path):
    downloader, http, _, _ = make_downloader(tmp_path, [FakeResponse(404)])
    result = downloader.download("https://cdn/video.mp4", str(tmp_path / "video.mp4"))

    assert result.ok is False
    assert result.error == "HTTP 404"
    assert len(http.requests) == 1


def test_timeout_retries_until_exhausted(tmp_path):
    class TimeoutHttp:
        def __init__(self):
            self.calls = 0

        def get(self, url, headers=None, stream=True, timeout=None):
            self.calls += 1
            raise requests.Timeout("timeout")

    config = AppConfig(save_dir=tmp_path, max_retries=2)
    http = TimeoutHttp()
    downloader = VideoDownloader(
        {},
        RecordingLimiter(),
        config,
        retry_policy=RetryPolicy(attempts=2, base_delay=1.0, max_delay=4.0, jitter=0.0),
        sleep=lambda seconds: None,
        rng=random.Random(0),
        http=http,
    )

    result = downloader.download("https://cdn/video.mp4", str(tmp_path / "video.mp4"))

    assert result.ok is False
    assert http.calls == 2
    assert "重试 2 次后仍失败" in result.error
