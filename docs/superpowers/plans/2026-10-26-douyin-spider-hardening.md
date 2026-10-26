# 抖音爬虫完善实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有单条视频下载器上补齐持久化登录态、两级限频、下载重试/续传、批量断点续爬与风控识别。

**Architecture:** 保留 `DouyinSpider` 作为单条链接编排入口，拆出 `config`、`session`、`rate_limiter`、`downloader`、`batch` 五个职责单一的模块；CLI 只负责菜单、输入和进度展示。所有网络重试与限频逻辑都可注入时钟/HTTP 客户端，默认全部走单元测试。

**Tech Stack:** Python 3.10+、Playwright sync API、requests、prompt_toolkit、pytest。

---

## 开始前检查（Pre-flight）

当前工作区有未提交改动，且本计划会重写 `cli.py`、`douyin_spider.py`、`test_spider.py`。开始前必须确认这些改动是否需要保留：

- [ ] **Step 1: 查看工作区状态**

Run:
```bash
git status --short
```

Expected: 能看到 `M cli.py`、`M douyin_spider.py`、`M test_spider.py`、`D draw/455.png`、`?? .codewhale/`。

- [ ] **Step 2: 检查待重写文件的现有改动**

Run:
```bash
git diff -- cli.py douyin_spider.py test_spider.py
```

Expected: 显示现有未提交改动。若其中有需要保留的内容，先单独备份或提交；本计划按当前文件内容重写。不要提交 `draw/455.png`、`.codewhale/`，后续每个任务只 `git add` 计划中列出的文件。

---

## 文件结构

- Create `config.py`：默认配置、`config.json` 加载/保存、固定路径。
- Create `session.py`：持久化浏览器上下文、登录检测、登录等待。
- Create `rate_limiter.py`：间隔限频与全局冷却。
- Create `downloader.py`：HTTP 下载、重试、Range 续传、大小校验。
- Create `batch.py`：批量队列、去重、状态文件、失败重试。
- Rewrite `douyin_spider.py`：单条链接状态机、风控识别、直链嗅探。
- Modify `cli.py`：登录、批量、重试失败项菜单与进度输出。
- Modify `stealth.min.js`：补充浏览器指纹字段。
- Create `test_config.py`、`test_rate_limiter.py`、`test_downloader.py`、`test_session.py`、`test_batch.py`、`test_cli.py`。
- Rewrite `test_spider.py`：更新为新接口的单元测试。
- Modify `requirements-dev.txt`：加入 `pytest`。
- Modify `setup.cmd`：Python 版本提示改为 3.10+。
- Rewrite `README.md`：登录、批量、配置、风控与合规说明。

---

### Task 0: 测试环境准备

**Files:**
- Modify: `requirements-dev.txt`
- Test: `test_spider.py`（现有测试）

- [ ] **Step 1: 在 dev 依赖中加入 pytest**

`requirements-dev.txt` 改为：

```text
pyinstaller
pytest
```

- [ ] **Step 2: 安装依赖**

Run:
```bash
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Expected: 安装成功，`pytest` 已存在或新安装。

- [ ] **Step 3: 运行现有测试确认基线**

Run:
```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: `13 passed`。

- [ ] **Step 4: 提交**

```bash
git add requirements-dev.txt
git commit -m "chore: 测试依赖加入 pytest

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 1: 配置模块

**Files:**
- Create: `config.py`
- Test: `test_config.py`

- [ ] **Step 1: 编写失败测试**

`test_config.py`：

```python
import json

from config import AppConfig, load_config, save_config


def test_load_config_creates_default_file(tmp_path):
    path = tmp_path / "config.json"
    config = load_config(path, cwd=tmp_path)
    assert path.exists()
    assert config.save_dir == (tmp_path / "videos").resolve()
    assert config.headless is False
    assert config.page_delay == (4.0, 9.0)
    assert config.max_retries == 3


def test_load_config_reads_overrides(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "save_dir": "downloads",
                "headless": True,
                "page_delay": [1, 2],
                "download_delay": [0.5, 1.5],
                "max_retries": 5,
                "cooldown_seconds": 30,
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path, cwd=tmp_path)
    assert config.save_dir == (tmp_path / "downloads").resolve()
    assert config.headless is True
    assert config.page_delay == (1.0, 2.0)
    assert config.download_delay == (0.5, 1.5)
    assert config.max_retries == 5
    assert config.cooldown_seconds == 30.0


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "page_delay": ["x", 2],
                "download_delay": [5, 1],
                "max_retries": "many",
                "headless": "yes",
                "chunk_size": -1,
                "human_behavior": "true",
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path, cwd=tmp_path)
    assert config.page_delay == (4.0, 9.0)
    assert config.download_delay == (1.0, 2.0)
    assert config.max_retries == 3
    assert config.headless is False
    assert config.chunk_size == 65536
    assert config.human_behavior is True


def test_save_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig(save_dir=tmp_path / "videos", headless=True)
    save_config(config, path)
    loaded = load_config(path, cwd=tmp_path)
    assert loaded.headless is True
    assert loaded.save_dir == (tmp_path / "videos").resolve()
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_config.py -q
```

Expected: 收集阶段报 `ModuleNotFoundError: No module named 'config'`。

- [ ] **Step 3: 实现 `config.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_DIR = Path.home() / ".douyin-spider"
CONFIG_PATH = APP_DIR / "config.json"
PROFILE_DIR = APP_DIR / "profile"
STATE_PATH = APP_DIR / "state.json"

DEFAULT_PAGE_DELAY = (4.0, 9.0)
DEFAULT_DOWNLOAD_DELAY = (1.0, 2.0)


@dataclass
class AppConfig:
    save_dir: Path
    headless: bool = False
    page_delay: tuple[float, float] = DEFAULT_PAGE_DELAY
    download_delay: tuple[float, float] = DEFAULT_DOWNLOAD_DELAY
    cooldown_seconds: float = 90.0
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 8.0
    page_timeout_ms: int = 60000
    video_wait_timeout_ms: int = 15000
    login_timeout_seconds: float = 180.0
    min_video_size: int = 1048576
    chunk_size: int = 65536
    human_behavior: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "save_dir": str(self.save_dir),
            "headless": self.headless,
            "page_delay": list(self.page_delay),
            "download_delay": list(self.download_delay),
            "cooldown_seconds": self.cooldown_seconds,
            "max_retries": self.max_retries,
            "backoff_base": self.backoff_base,
            "backoff_max": self.backoff_max,
            "page_timeout_ms": self.page_timeout_ms,
            "video_wait_timeout_ms": self.video_wait_timeout_ms,
            "login_timeout_seconds": self.login_timeout_seconds,
            "min_video_size": self.min_video_size,
            "chunk_size": self.chunk_size,
            "human_behavior": self.human_behavior,
        }


def _absolute_save_dir(raw: Any, cwd: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        return (cwd / "videos").resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def _pair(raw: Any, default: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return default
    try:
        low, high = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return default
    if low < 0 or high < low:
        return default
    return (low, high)


def _number(raw: Any, default: float, *, minimum: float = 0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _integer(raw: Any, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _boolean(raw: Any, default: bool) -> bool:
    return raw if isinstance(raw, bool) else default


def load_config(
    path: Path = CONFIG_PATH,
    *,
    cwd: Path | None = None,
    write_if_missing: bool = True,
) -> AppConfig:
    cwd = Path(cwd or Path.cwd())
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("配置根节点必须是对象")
            data = loaded
        except (OSError, ValueError) as exc:
            print(f"[Config] 读取配置失败，使用默认值: {exc}")
            data = {}

    config = AppConfig(
        save_dir=_absolute_save_dir(data.get("save_dir"), cwd),
        headless=_boolean(data.get("headless"), False),
        page_delay=_pair(data.get("page_delay"), DEFAULT_PAGE_DELAY),
        download_delay=_pair(data.get("download_delay"), DEFAULT_DOWNLOAD_DELAY),
        cooldown_seconds=_number(data.get("cooldown_seconds"), 90.0),
        max_retries=_integer(data.get("max_retries"), 3),
        backoff_base=_number(data.get("backoff_base"), 1.0),
        backoff_max=_number(data.get("backoff_max"), 8.0),
        page_timeout_ms=_integer(data.get("page_timeout_ms"), 60000),
        video_wait_timeout_ms=_integer(data.get("video_wait_timeout_ms"), 15000),
        login_timeout_seconds=_number(data.get("login_timeout_seconds"), 180.0),
        min_video_size=_integer(data.get("min_video_size"), 1048576),
        chunk_size=_integer(data.get("chunk_size"), 65536),
        human_behavior=_boolean(data.get("human_behavior"), True),
    )

    if write_if_missing and not path.exists():
        save_config(config, path)
    return config


def save_config(config: AppConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_config.py -q
```

Expected: `4 passed`。

- [ ] **Step 5: 提交**

```bash
git add config.py test_config.py
git commit -m "feat: 添加配置模块与配置文件读写

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 限频器

**Files:**
- Create: `rate_limiter.py`
- Test: `test_rate_limiter.py`

- [ ] **Step 1: 编写失败测试**

`test_rate_limiter.py`：

```python
import pytest

from rate_limiter import IntervalPolicy, RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FixedRng:
    def __init__(self, value):
        self.value = value

    def uniform(self, low, high):
        return self.value


def make_limiter(policy, clock, value):
    return RateLimiter(
        policy,
        clock=clock,
        sleep=clock.sleep,
        rng=FixedRng(value),
    )


def test_first_wait_does_not_sleep():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(2, 4), clock, 3)
    assert limiter.wait() == 0.0
    assert clock.now == 0.0


def test_second_wait_uses_interval():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(2, 4), clock, 3)
    limiter.wait()
    assert limiter.wait() == 3.0
    assert clock.now == 3.0


def test_block_for_delays_next_wait():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(1, 1), clock, 1)
    limiter.wait()
    limiter.block_for(10)
    assert limiter.wait() == 10.0
    assert clock.now == 10.0


def test_block_for_does_not_shorten_existing_block():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(1, 1), clock, 1)
    limiter.wait()
    limiter.block_for(10)
    limiter.block_for(5)
    assert limiter.wait() == 10.0


def test_invalid_policy_raises():
    with pytest.raises(ValueError):
        IntervalPolicy(3, 2)
    with pytest.raises(ValueError):
        IntervalPolicy(-1, 2)
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_rate_limiter.py -q
```

Expected: `ModuleNotFoundError: No module named 'rate_limiter'`。

- [ ] **Step 3: 实现 `rate_limiter.py`**

```python
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class IntervalPolicy:
    min_seconds: float
    max_seconds: float

    def __post_init__(self) -> None:
        if self.min_seconds < 0 or self.max_seconds < self.min_seconds:
            raise ValueError("限频区间不合法")


class RateLimiter:
    def __init__(
        self,
        policy: IntervalPolicy,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ):
        self.policy = policy
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._last: float | None = None
        self._blocked_until = 0.0

    def wait(self) -> float:
        now = self._clock()
        target = now
        if self._last is not None:
            target = self._last + self._rng.uniform(
                self.policy.min_seconds,
                self.policy.max_seconds,
            )
        target = max(target, self._blocked_until)
        delay = max(0.0, target - now)
        if delay > 0:
            self._sleep(delay)
        self._last = self._clock()
        return delay

    def block_for(self, seconds: float) -> None:
        until = self._clock() + max(0.0, seconds)
        self._blocked_until = max(self._blocked_until, until)
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_rate_limiter.py -q
```

Expected: `5 passed`。

- [ ] **Step 5: 提交**

```bash
git add rate_limiter.py test_rate_limiter.py
git commit -m "feat: 添加页面与下载限频器

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 下载器

**Files:**
- Create: `downloader.py`
- Test: `test_downloader.py`
- Depends on: `config.py`、`rate_limiter.py`

- [ ] **Step 1: 编写失败测试**

`test_downloader.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_downloader.py -q
```

Expected: `ModuleNotFoundError: No module named 'downloader'`。

- [ ] **Step 3: 实现 `downloader.py`**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_downloader.py -q
```

Expected: `9 passed`。

- [ ] **Step 5: 提交**

```bash
git add downloader.py test_downloader.py
git commit -m "feat: 添加下载重试、续传与大小校验

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 浏览器会话与登录态

**Files:**
- Create: `session.py`
- Test: `test_session.py`
- Depends on: `config.py`

- [ ] **Step 1: 编写失败测试**

`test_session.py`：

```python
from pathlib import Path

from config import AppConfig
from session import BrowserSession


def test_is_logged_in_cookies():
    assert BrowserSession.is_logged_in_cookies([{"name": "sessionid"}]) is True
    assert BrowserSession.is_logged_in_cookies([{"name": "sessionid_ss"}]) is True
    assert BrowserSession.is_logged_in_cookies([{"name": "ttwid"}]) is False
    assert BrowserSession.is_logged_in_cookies([]) is False


def test_stealth_path_points_to_project_file(tmp_path):
    session = BrowserSession(
        AppConfig(save_dir=tmp_path),
        profile_dir=tmp_path / "profile",
    )
    assert session._stealth_path() == Path(__file__).resolve().parent / "stealth.min.js"
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_session.py -q
```

Expected: `ModuleNotFoundError: No module named 'session'`。

- [ ] **Step 3: 实现 `session.py`**

```python
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import BrowserContext, sync_playwright

from config import AppConfig, PROFILE_DIR

DOUYIN_HOME = "https://www.douyin.com/"
LOGIN_COOKIE_NAMES = {"sessionid", "sessionid_ss"}


class BrowserSession:
    def __init__(
        self,
        config: AppConfig,
        *,
        profile_dir: Path = PROFILE_DIR,
        log: Callable[[str], None] = print,
    ):
        self.config = config
        self.profile_dir = Path(profile_dir)
        self.log = log
        self._playwright = None
        self._context: BrowserContext | None = None

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            self.start()
        assert self._context is not None
        return self._context

    def start(self) -> BrowserContext:
        if self._context is not None:
            return self._context

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.config.headless,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                viewport={"width": 1920, "height": 1080},
            )
        except Exception as exc:
            self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                "浏览器启动失败：请关闭其他正在使用该 profile 的程序后重试"
            ) from exc

        self._context = context
        stealth = self._stealth_path()
        if stealth.exists():
            self.log(f"加载反爬脚本: {stealth}")
            context.add_init_script(path=str(stealth))
        else:
            self.log("警告: 未找到反爬脚本 stealth.min.js")
        return context

    def _stealth_path(self) -> Path:
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS"))
            return base / "stealth.min.js"
        return Path(__file__).resolve().parent / "stealth.min.js"

    @staticmethod
    def is_logged_in_cookies(cookies: list[dict]) -> bool:
        return any(cookie.get("name") in LOGIN_COOKIE_NAMES for cookie in cookies)

    def is_logged_in(self) -> bool:
        return self.is_logged_in_cookies(self.context.cookies(DOUYIN_HOME))

    def ensure_login(
        self,
        prompt_callback: Callable[[str], None] | None = None,
    ) -> bool:
        if self.is_logged_in():
            return True
        if self.config.headless:
            return False

        page = self.context.new_page()
        try:
            page.goto(
                DOUYIN_HOME,
                wait_until="domcontentloaded",
                timeout=self.config.page_timeout_ms,
            )
            if prompt_callback:
                prompt_callback("请在打开的浏览器中扫码登录，登录成功后会自动继续。")
            deadline = time.monotonic() + self.config.login_timeout_seconds
            while time.monotonic() < deadline:
                if self.is_logged_in():
                    return True
                time.sleep(2)
            return False
        finally:
            page.close()

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_session.py -q
```

Expected: `2 passed`。

- [ ] **Step 5: 提交**

```bash
git add session.py test_session.py
git commit -m "feat: 添加持久化浏览器会话与登录检测

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 单条链接抓取重构

**Files:**
- Rewrite: `douyin_spider.py`
- Rewrite: `test_spider.py`
- Depends on: Task 1-4

- [ ] **Step 1: 用新测试替换 `test_spider.py`**

```python
from config import AppConfig
from douyin_spider import DouyinSpider, extract_url_from_text


def make_spider(tmp_path):
    return DouyinSpider(
        "https://v.douyin.com/abc/",
        session=object(),
        config=AppConfig(save_dir=tmp_path),
        log_callback=lambda message: None,
    )


class FakeResponse:
    def __init__(
        self,
        url,
        *,
        status=200,
        content_type="video/mp4",
        size=2 * 1024 * 1024,
    ):
        self.url = url
        self.status = status
        self.headers = {
            "content-type": content_type,
            "content-length": str(size),
        }


class TestExtractUrlFromText:
    def test_extract_http_url(self):
        result = extract_url_from_text("https://v.douyin.com/abc123/")
        assert result == "https://v.douyin.com/abc123/"

    def test_extract_url_from_mixed_text(self):
        text = "这是抖音分享链接 https://v.douyin.com/xyz789/ 快来看看"
        result = extract_url_from_text(text)
        assert result == "https://v.douyin.com/xyz789/"

    def test_extract_first_url_when_multiple(self):
        result = extract_url_from_text(
            "https://v.douyin.com/first/ and https://v.douyin.com/second/"
        )
        assert result == "https://v.douyin.com/first/"

    def test_no_url_returns_none(self):
        result = extract_url_from_text("这只是一段普通文本没有链接")
        assert result is None

    def test_empty_string(self):
        assert extract_url_from_text("") is None

    def test_extract_with_emoji(self):
        text = "😎🔥 https://v.douyin.com/test/ 🔥😎"
        assert extract_url_from_text(text) == "https://v.douyin.com/test/"


class TestParseVideoId:
    def test_long_video_url(self):
        assert (
            DouyinSpider.parse_video_id("https://www.douyin.com/video/7123456789")
            == "7123456789"
        )

    def test_note_url(self):
        assert (
            DouyinSpider.parse_video_id("https://www.douyin.com/note/7123")
            == "7123"
        )

    def test_short_url_returns_none(self):
        assert DouyinSpider.parse_video_id("https://v.douyin.com/abc/") is None

    def test_searches_all_candidates(self):
        assert (
            DouyinSpider.parse_video_id(None, "https://x/video/123?foo=1")
            == "123"
        )


class TestRiskFromText:
    def test_captcha(self):
        assert DouyinSpider.risk_from_text("请完成验证后继续") == "captcha"

    def test_login(self):
        assert DouyinSpider.risk_from_text("登录后查看评论") == "login"

    def test_none(self):
        assert DouyinSpider.risk_from_text("普通页面") is None


class TestSanitizeFilename:
    def test_removes_illegal_chars(self):
        assert DouyinSpider._sanitize_filename("test:file*name?") == "testfilename"

    def test_strips_whitespace(self):
        assert DouyinSpider._sanitize_filename("  spaced  ") == "spaced"


class TestHandleResponse:
    def test_captures_large_video(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse("https://cdn.example.com/a.mp4")
        )
        assert len(spider.video_candidates) == 1
        assert spider.video_candidates[0]["url"] == "https://cdn.example.com/a.mp4"

    def test_ignores_small_file(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse("https://cdn.example.com/ad.mp4", size=1024)
        )
        assert spider.video_candidates == []

    def test_ignores_duplicate_url(self, tmp_path):
        spider = make_spider(tmp_path)
        response = FakeResponse("https://cdn.example.com/a.mp4")
        spider.handle_response(response)
        spider.handle_response(response)
        assert len(spider.video_candidates) == 1

    def test_ignores_non_video(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse(
                "https://www.douyin.com/page",
                content_type="text/html",
            )
        )
        assert spider.video_candidates == []

    def test_ignores_non_200(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse("https://cdn.example.com/a.mp4", status=304)
        )
        assert spider.video_candidates == []


class TestSelectTarget:
    def test_returns_largest_candidate(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.video_candidates = [
            {"url": "small", "size": 1},
            {"url": "large", "size": 2},
        ]
        assert spider._select_target(None) == "large"

    def test_falls_back_to_video_element(self, tmp_path):
        class FakeVideo:
            def get_attribute(self, name):
                if name == "src":
                    return "https://cdn.example.com/fallback.mp4"
                return None

            def query_selector_all(self, selector):
                return []

        class FakePage:
            def query_selector(self, selector):
                return FakeVideo()

        spider = make_spider(tmp_path)
        assert (
            spider._select_target(FakePage())
            == "https://cdn.example.com/fallback.mp4"
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_spider.py -q
```

Expected: 失败，`DouyinSpider` 仍是旧构造函数，报 `TypeError` 或缺少 `parse_video_id` / `risk_from_text`。

- [ ] **Step 3: 重写 `douyin_spider.py`**

```python
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from playwright.sync_api import (
    Page,
    Response,
    TimeoutError as PlaywrightTimeoutError,
)

from config import AppConfig, load_config
from downloader import LinkExpiredError, VideoDownloader
from rate_limiter import IntervalPolicy, RateLimiter
from session import BrowserSession

DOWNLOAD_HEADERS = {"Referer": "https://www.douyin.com/"}


@dataclass
class FetchResult:
    ok: bool
    url: str
    video_id: str | None = None
    title: str | None = None
    filepath: str | None = None
    size: int = 0
    error: str | None = None
    risk: str | None = None
    skipped: bool = False


@dataclass
class _SniffResult:
    target_url: str | None = None
    title: str | None = None
    video_id: str | None = None
    risk: str | None = None
    error: str | None = None


class DouyinSpider:
    MAX_TITLE_LEN = 50
    MANUAL_RISK_WAIT_SECONDS = 120
    RISK_KEYWORDS = ("验证码", "安全验证", "请完成验证", "登录后查看")
    RISK_SELECTORS = (
        "#captcha_container",
        ".captcha_verify_container",
        ".verify-bar",
    )
    VIDEO_ID_RE = re.compile(r"/(?:video|note)/(\d+)")

    def __init__(
        self,
        url: str,
        *,
        session: BrowserSession,
        config: AppConfig,
        log_callback: Callable[[str], None] | None = None,
        page_limiter: RateLimiter | None = None,
        download_limiter: RateLimiter | None = None,
        downloader: VideoDownloader | None = None,
    ):
        self.url = url
        self.session = session
        self.config = config
        self.log_callback = log_callback
        self.page_limiter = page_limiter or RateLimiter(
            IntervalPolicy(*config.page_delay)
        )
        self.download_limiter = download_limiter or RateLimiter(
            IntervalPolicy(*config.download_delay)
        )
        self.video_candidates: list[dict] = []
        self.save_dir = Path(config.save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.downloader = downloader or VideoDownloader(
            DOWNLOAD_HEADERS,
            self.download_limiter,
            config,
        )

    def log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[Spider] {message}")

    def handle_response(self, response: Response) -> None:
        try:
            if response.status != 200:
                return
            content_type = response.headers.get("content-type", "")
            if "video/mp4" not in content_type and ".mp4" not in response.url:
                return
            content_length = int(response.headers.get("content-length", 0) or 0)
            url = response.url
            if content_length <= self.config.min_video_size:
                self.log(
                    f"忽略小文件(可能是广告): 大小={content_length / 1024:.0f}KB, "
                    f"URL={url[:60]}..."
                )
                return
            if any(item["url"] == url for item in self.video_candidates):
                return
            self.log(
                f"捕获视频流: 大小={content_length / 1024 / 1024:.2f}MB, "
                f"URL={url[:60]}..."
            )
            self.video_candidates.append({"url": url, "size": content_length})
        except Exception as exc:
            self.log(f"处理响应时出错: {exc}")

    def fetch(self, skip_video_ids: set[str] | None = None) -> FetchResult:
        skip_video_ids = skip_video_ids or set()
        page = None
        try:
            page = self.session.context.new_page()
            page.on("response", self.handle_response)
            return self._fetch_with_resniff(page, skip_video_ids)
        except Exception as exc:
            self.log(f"抓取失败: {exc}")
            return FetchResult(False, self.url, error=str(exc))
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass

    def _fetch_with_resniff(
        self,
        page: Page,
        skip_video_ids: set[str],
    ) -> FetchResult:
        sniff: _SniffResult | None = None
        for _ in range(3):
            self.video_candidates.clear()
            sniff = self._open_and_sniff(page)
            if sniff.risk:
                return FetchResult(
                    False,
                    self.url,
                    error=self._risk_message(sniff.risk),
                    risk=sniff.risk,
                )
            if not sniff.target_url:
                return FetchResult(
                    False,
                    self.url,
                    video_id=sniff.video_id,
                    title=sniff.title,
                    error=sniff.error or "未获取到视频直链",
                )
            if sniff.video_id and sniff.video_id in skip_video_ids:
                return FetchResult(
                    True,
                    self.url,
                    video_id=sniff.video_id,
                    title=sniff.title,
                    skipped=True,
                )

            filename = sniff.title or f"douyin_{int(time.time())}"
            filepath = self.save_dir / f"{filename}.mp4"
            self.download_limiter.wait()
            try:
                result = self.downloader.download(sniff.target_url, str(filepath))
            except LinkExpiredError as exc:
                self.log(f"直链已过期（{exc}），重新嗅探...")
                continue

            if result.ok:
                return FetchResult(
                    True,
                    self.url,
                    video_id=sniff.video_id,
                    title=sniff.title,
                    filepath=result.path,
                    size=result.bytes_written,
                )
            return FetchResult(
                False,
                self.url,
                video_id=sniff.video_id,
                title=sniff.title,
                error=result.error,
            )

        return FetchResult(
            False,
            self.url,
            video_id=sniff.video_id if sniff else None,
            title=sniff.title if sniff else None,
            error="直链多次过期，放弃下载",
        )

    def _open_and_sniff(self, page: Page) -> _SniffResult:
        if not self._navigate(page):
            return _SniffResult(error=f"页面加载失败: {self.url}")

        self._sync_user_agent(page)

        risk = self._detect_risk(page)
        if risk:
            risk = self._wait_for_manual_fix(page, risk)
            if risk:
                return _SniffResult(
                    risk=risk,
                    error=self._risk_message(risk),
                )

        if not self.video_candidates:
            try:
                page.wait_for_selector(
                    "video",
                    timeout=self.config.video_wait_timeout_ms,
                )
            except PlaywrightTimeoutError:
                if self.config.human_behavior:
                    self._simulate_human(page)
                try:
                    page.wait_for_selector(
                        "video",
                        timeout=self.config.video_wait_timeout_ms,
                    )
                except PlaywrightTimeoutError:
                    self.log("等待视频元素超时")

        title = self._extract_title(page)
        target_url = self._select_target(page)
        video_id = self.parse_video_id(page.url, target_url, self.url)
        if not target_url:
            return _SniffResult(
                title=title,
                video_id=video_id,
                error="未捕获到视频直链",
            )
        return _SniffResult(
            target_url=target_url,
            title=title,
            video_id=video_id,
        )

    def _navigate(self, page: Page) -> bool:
        for attempt in range(2):
            self.page_limiter.wait()
            try:
                page.goto(
                    self.url,
                    wait_until="domcontentloaded",
                    timeout=self.config.page_timeout_ms,
                )
                return True
            except PlaywrightTimeoutError as exc:
                self.log(f"页面加载超时（第 {attempt + 1} 次）: {exc}")
        return False

    def _sync_user_agent(self, page: Page) -> None:
        try:
            user_agent = page.evaluate("navigator.userAgent")
        except Exception:
            return
        headers = getattr(self.downloader, "headers", None)
        if isinstance(user_agent, str) and user_agent and isinstance(headers, dict):
            headers["User-Agent"] = user_agent

    def _detect_risk(self, page: Page) -> str | None:
        if "login" in page.url.lower():
            return "login"
        for selector in self.RISK_SELECTORS:
            try:
                if page.locator(selector).count() > 0:
                    return "captcha"
            except Exception:
                continue
        try:
            text = page.locator("body").inner_text(timeout=2000)
        except Exception:
            text = ""
        return self.risk_from_text(text)

    @classmethod
    def risk_from_text(cls, text: str) -> str | None:
        if not text:
            return None
        if any(keyword in text for keyword in ("验证码", "安全验证", "请完成验证")):
            return "captcha"
        if "登录后查看" in text:
            return "login"
        return None

    def _wait_for_manual_fix(self, page: Page, risk: str) -> str | None:
        if self.config.headless:
            return risk
        self.log(
            f"检测到风控（{risk}），请在浏览器中手动登录或完成验证，"
            f"最多等待 {self.MANUAL_RISK_WAIT_SECONDS} 秒..."
        )
        deadline = time.monotonic() + self.MANUAL_RISK_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(2)
            if self._detect_risk(page) is None:
                self.log("风控状态已解除，继续抓取。")
                return None
        return risk

    @staticmethod
    def _risk_message(risk: str) -> str:
        if risk == "login":
            return "需要登录：请先执行登录，或切换到有头模式手动登录"
        if risk == "captcha":
            return "触发安全验证：请切换到有头模式手动完成验证"
        return "触发风控"

    def _simulate_human(self, page: Page) -> None:
        rng = random.Random()
        for _ in range(rng.randint(1, 3)):
            page.mouse.move(
                rng.randint(50, 1800),
                rng.randint(100, 900),
                steps=rng.randint(5, 15),
            )
            page.mouse.wheel(0, rng.randint(100, 500))
            time.sleep(rng.uniform(1.0, 3.0))

    def _extract_title(self, page: Page) -> str:
        title = self._sanitize_filename(page.title())
        if not title or title == "抖音":
            try:
                title = self._sanitize_filename(
                    page.locator(".desc").first.inner_text(timeout=3000)
                )
            except Exception:
                pass
        if not title or title == "抖音":
            title = f"douyin_{int(time.time())}"
        return title[: self.MAX_TITLE_LEN]

    def _select_target(self, page: Page | None) -> str | None:
        if self.video_candidates:
            best = max(self.video_candidates, key=lambda item: item["size"])
            self.log(
                f"从 {len(self.video_candidates)} 个候选中选择最大文件: "
                f"{best['url'][:60]}..."
            )
            return best["url"]

        self.log("网络监听未捕获有效视频，尝试解析 video 元素...")
        if page is None:
            return None
        try:
            video = page.query_selector("video")
            if video:
                src = video.get_attribute("src")
                if src and src.startswith("http"):
                    return src
                for source in video.query_selector_all("source"):
                    src = source.get_attribute("src")
                    if src and src.startswith("http"):
                        return src
        except Exception as exc:
            self.log(f"解析 video 元素失败: {exc}")
        return None

    @classmethod
    def parse_video_id(cls, *urls: str | None) -> str | None:
        for url in urls:
            if not url:
                continue
            match = cls.VIDEO_ID_RE.search(url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', "", filename).strip()

    def run(self) -> None:
        result = self.fetch()
        if result.ok:
            self.log(f"下载完成！文件已保存至: {result.filepath}")
        else:
            self.log(f"抓取失败: {result.error}")


def extract_url_from_text(text: str) -> str | None:
    urls = re.findall(
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|"
        r"(?:%[0-9a-fA-F][0-9a-fA-F]))+",
        text,
    )
    if urls:
        return urls[0]
    return None


if __name__ == "__main__":
    print("=" * 50)
    print("抖音视频学习爬虫 (Playwright版)")
    print("注意：本脚本仅供学习交流，请勿用于非法用途")
    print("=" * 50)

    raw_input = input("请粘贴抖音分享文本 (包含链接即可): ")
    if raw_input:
        target_url = extract_url_from_text(raw_input)
        if target_url:
            print(f"识别到链接: {target_url}")
            config = load_config()
            session = BrowserSession(config)
            try:
                spider = DouyinSpider(target_url, session=session, config=config)
                spider.run()
            finally:
                session.close()
        else:
            print("未在输入中识别到有效的 http/https 链接")
    else:
        print("未输入内容，程序退出")
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_spider.py -q
```

Expected: `22 passed`。

- [ ] **Step 5: 提交**

```bash
git add douyin_spider.py test_spider.py
git commit -m "feat: 重构单条抓取流程并加入风控识别

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 批量队列与断点状态

**Files:**
- Create: `batch.py`
- Test: `test_batch.py`
- Depends on: Task 1、Task 5

- [ ] **Step 1: 编写失败测试**

`test_batch.py`：

```python
from batch import (
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_SUCCESS,
    BatchItem,
    BatchRunner,
    StateStore,
)
from config import AppConfig
from douyin_spider import FetchResult


class FakeSpider:
    def __init__(self, result):
        self.result = result
        self.seen_skip_ids = None

    def fetch(self, skip_video_ids=None):
        self.seen_skip_ids = skip_video_ids
        return self.result


def make_runner(tmp_path, results):
    config = AppConfig(save_dir=tmp_path)
    store = StateStore(tmp_path / "state.json", log=lambda message: None)
    spiders = []

    def factory(url):
        spider = FakeSpider(results[url])
        spiders.append(spider)
        return spider

    runner = BatchRunner(
        None,
        config,
        store,
        spider_factory=factory,
        log=lambda message: None,
    )
    return runner, store, spiders


def success(url, video_id="1", title="video"):
    return FetchResult(
        ok=True,
        url=url,
        video_id=video_id,
        title=title,
        filepath=f"/tmp/{title}.mp4",
        size=10,
    )


def test_state_store_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path, log=lambda message: None)
    store.upsert(
        BatchItem(
            url="https://a",
            status=STATUS_SUCCESS,
            video_id="1",
            title="t",
        )
    )
    store.save()

    loaded = StateStore(path, log=lambda message: None)
    loaded.load()

    item = loaded.get("https://a")
    assert item is not None
    assert item.status == STATUS_SUCCESS
    assert item.video_id == "1"
    assert not (tmp_path / "state.json.tmp").exists()


def test_success_video_ids_and_failed_urls(tmp_path):
    store = StateStore(tmp_path / "state.json", log=lambda message: None)
    store.upsert(BatchItem(url="https://a", status=STATUS_SUCCESS, video_id="1"))
    store.upsert(BatchItem(url="https://b", status=STATUS_FAILED, error="boom"))

    assert store.success_video_ids() == {"1"}
    assert store.failed_urls() == ["https://b"]


def test_corrupt_state_file_is_backed_up(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    store = StateStore(path, log=lambda message: None)

    store.load()

    assert store.items == {}
    assert (tmp_path / "state.json.bak").exists()


def test_runner_downloads_and_saves_success(tmp_path):
    url = "https://v.douyin.com/a/"
    runner, store, spiders = make_runner(tmp_path, {url: success(url)})

    summary = runner.run([url])

    assert summary.success == 1
    assert store.get(url).status == STATUS_SUCCESS
    assert store.get(url).file.endswith("video.mp4")
    assert (tmp_path / "state.json").exists()
    assert len(spiders) == 1


def test_runner_skips_existing_success(tmp_path):
    url = "https://v.douyin.com/a/"
    runner, store, spiders = make_runner(tmp_path, {})
    store.upsert(BatchItem(url=url, status=STATUS_SUCCESS, title="done"))

    summary = runner.run([url])

    assert summary.skipped == 1
    assert spiders == []


def test_runner_retry_failed_only(tmp_path):
    ok_url = "https://v.douyin.com/ok/"
    bad_url = "https://v.douyin.com/bad/"
    runner, store, spiders = make_runner(
        tmp_path,
        {bad_url: success(bad_url, video_id="2")},
    )
    store.upsert(BatchItem(url=ok_url, status=STATUS_SUCCESS, video_id="1"))
    store.upsert(BatchItem(url=bad_url, status=STATUS_FAILED, error="boom"))

    summary = runner.run(None, retry_failed=True)

    assert summary.total == 1
    assert summary.success == 1
    assert store.get(bad_url).status == STATUS_SUCCESS
    assert len(spiders) == 1


def test_runner_marks_duplicate_video_id_as_skipped(tmp_path):
    old_url = "https://v.douyin.com/old/"
    new_url = "https://v.douyin.com/new/"
    duplicate = FetchResult(
        ok=True,
        url=new_url,
        video_id="42",
        title="same video",
        skipped=True,
    )
    runner, store, spiders = make_runner(tmp_path, {new_url: duplicate})
    store.upsert(BatchItem(url=old_url, status=STATUS_SUCCESS, video_id="42"))

    summary = runner.run([new_url])

    assert summary.skipped == 1
    assert store.get(new_url).status == STATUS_DUPLICATE
    assert spiders[0].seen_skip_ids == {"42"}


def test_runner_continues_after_spider_exception(tmp_path):
    bad_url = "https://v.douyin.com/bad/"
    ok_url = "https://v.douyin.com/ok/"
    config = AppConfig(save_dir=tmp_path)
    store = StateStore(tmp_path / "state.json", log=lambda message: None)

    def factory(url):
        if url == bad_url:
            raise RuntimeError("boom")
        return FakeSpider(success(url))

    runner = BatchRunner(
        None,
        config,
        store,
        spider_factory=factory,
        log=lambda message: None,
    )

    summary = runner.run([bad_url, ok_url])

    assert summary.failed == 1
    assert summary.success == 1
    assert store.get(bad_url).status == STATUS_FAILED
    assert store.get(ok_url).status == STATUS_SUCCESS
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_batch.py -q
```

Expected: `ModuleNotFoundError: No module named 'batch'`。

- [ ] **Step 3: 实现 `batch.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from config import STATE_PATH
from douyin_spider import DouyinSpider

STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_DUPLICATE = "skipped_duplicate"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class BatchItem:
    url: str
    status: str = STATUS_PENDING
    video_id: str | None = None
    title: str | None = None
    file: str | None = None
    size: int = 0
    attempts: int = 0
    error: str | None = None
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "BatchItem":
        return cls(
            url=str(data.get("url", "")),
            status=str(data.get("status", STATUS_PENDING)),
            video_id=data.get("video_id"),
            title=data.get("title"),
            file=data.get("file"),
            size=int(data.get("size", 0) or 0),
            attempts=int(data.get("attempts", 0) or 0),
            error=data.get("error"),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass
class BatchSummary:
    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    failed_urls: list[str] = field(default_factory=list)


class StateStore:
    def __init__(
        self,
        path: Path = STATE_PATH,
        *,
        log: Callable[[str], None] = print,
    ):
        self.path = Path(path)
        self.log = log
        self.items: dict[str, BatchItem] = {}

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("状态根节点必须是对象")
            raw_items = payload.get("items", {})
            if not isinstance(raw_items, dict):
                raise ValueError("items 必须是对象")
            self.items = {}
            for url, raw in raw_items.items():
                if not isinstance(raw, dict):
                    continue
                data = dict(raw)
                data.setdefault("url", url)
                self.items[url] = BatchItem.from_dict(data)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            backup = self.path.with_suffix(".json.bak")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.items = {}
            self.log(f"[State] 状态文件损坏，已备份到 {backup}: {exc}")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "items": {
                url: asdict(item)
                for url, item in self.items.items()
            },
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def get(self, url: str) -> BatchItem | None:
        return self.items.get(url)

    def upsert(self, item: BatchItem) -> None:
        self.items[item.url] = item

    def success_video_ids(self) -> set[str]:
        return {
            item.video_id
            for item in self.items.values()
            if item.status == STATUS_SUCCESS and item.video_id
        }

    def failed_urls(self) -> list[str]:
        return [
            item.url
            for item in self.items.values()
            if item.status == STATUS_FAILED
        ]


class BatchRunner:
    def __init__(
        self,
        session,
        config,
        store: StateStore,
        *,
        spider_factory: Callable[[str], object] | None = None,
        log: Callable[[str], None] = print,
    ):
        self.session = session
        self.config = config
        self.store = store
        self.log = log
        self._spider_factory = spider_factory or self._default_spider

    def _default_spider(self, url: str) -> DouyinSpider:
        return DouyinSpider(
            url,
            session=self.session,
            config=self.config,
            log_callback=self.log,
        )

    def run(
        self,
        urls: Iterable[str] | None = None,
        *,
        force: bool = False,
        retry_failed: bool = False,
    ) -> BatchSummary:
        if retry_failed and not urls:
            urls = self.store.failed_urls()
        unique = list(
            dict.fromkeys(
                url.strip()
                for url in (urls or [])
                if url and url.strip()
            )
        )
        summary = BatchSummary(total=len(unique))

        for index, url in enumerate(unique, start=1):
            existing = self.store.get(url)
            if not force and existing and existing.status == STATUS_SUCCESS:
                summary.skipped += 1
                self.log(
                    f"[{index}/{len(unique)}] 跳过（已完成）: "
                    f"{existing.title or url}"
                )
                continue

            item = existing or BatchItem(url=url)
            item.url = url
            item.attempts += 1
            item.updated_at = now_iso()
            self.log(f"[{index}/{len(unique)}] 开始: {url}")

            try:
                spider = self._spider_factory(url)
                result = spider.fetch(
                    skip_video_ids=self.store.success_video_ids()
                )
            except Exception as exc:
                item.status = STATUS_FAILED
                item.error = f"未预期错误: {exc}"
                summary.failed += 1
                summary.failed_urls.append(url)
                self.store.upsert(item)
                self._safe_save()
                self.log(f"[{index}/{len(unique)}] 失败: {item.error}")
                continue

            item.video_id = result.video_id or item.video_id
            item.title = result.title or item.title
            if result.skipped:
                item.status = STATUS_DUPLICATE
                item.error = None
                summary.skipped += 1
                self.log(
                    f"[{index}/{len(unique)}] 跳过（重复作品）: "
                    f"{item.title or url}"
                )
            elif result.ok:
                item.status = STATUS_SUCCESS
                item.file = result.filepath
                item.size = result.size
                item.error = None
                summary.success += 1
                self.log(f"[{index}/{len(unique)}] 成功: {item.title or url}")
            else:
                item.status = STATUS_FAILED
                item.error = result.error or "未知错误"
                summary.failed += 1
                summary.failed_urls.append(url)
                self.log(f"[{index}/{len(unique)}] 失败: {item.error}")

            self.store.upsert(item)
            self._safe_save()

        return summary

    def _safe_save(self) -> None:
        try:
            self.store.save()
        except OSError as exc:
            self.log(f"[State] 状态保存失败: {exc}")
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_batch.py -q
```

Expected: `8 passed`。

- [ ] **Step 5: 提交**

```bash
git add batch.py test_batch.py
git commit -m "feat: 添加批量队列、去重与断点状态

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: CLI 菜单与批量交互

**Files:**
- Modify: `cli.py`
- Test: `test_cli.py`
- Depends on: Task 1-6

- [ ] **Step 1: 编写失败测试**

`test_cli.py`：

```python
from cli import _collect_urls


def test_collect_urls_skips_invalid_lines(capsys):
    urls = _collect_urls(
        [
            "https://v.douyin.com/a/",
            "no link",
            "https://v.douyin.com/b/",
        ]
    )
    assert urls == [
        "https://v.douyin.com/a/",
        "https://v.douyin.com/b/",
    ]
    assert "第 2 行" in capsys.readouterr().out


def test_collect_urls_reads_file(tmp_path):
    path = tmp_path / "links.txt"
    path.write_text(
        "https://v.douyin.com/a/\n"
        "no link\n"
        "https://v.douyin.com/b/\n",
        encoding="utf-8",
    )
    assert _collect_urls([f"@{path}"]) == [
        "https://v.douyin.com/a/",
        "https://v.douyin.com/b/",
    ]


def test_collect_urls_reports_missing_file(tmp_path, capsys):
    urls = _collect_urls([f"@{tmp_path / 'missing.txt'}"])
    assert urls == []
    assert "无法读取文件" in capsys.readouterr().out
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_cli.py -q
```

Expected: `ImportError: cannot import name '_collect_urls'`。

- [ ] **Step 3: 用新实现替换 `cli.py`**

```python
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from batch import BatchRunner, StateStore
from config import load_config, save_config
from douyin_spider import extract_url_from_text
from session import BrowserSession

import os
import sys
import traceback

T = TypeVar("T")


def _tui_available() -> bool:
    try:
        import prompt_toolkit  # noqa: F401

        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _menu_tui(save_dir: str) -> str:
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    items = [
        ("login", "登录 / 检查登录状态"),
        ("batch", "开始批量爬取"),
        ("retry_failed", "重试失败项"),
        ("set_path", "配置下载路径"),
        ("quit", "退出"),
    ]
    state = {"index": 0}

    def _render():
        lines = []
        lines.append(("class:cwd", f"{os.getcwd()}\n\n"))
        lines.append(("class:muted", f"当前下载路径: {save_dir}\n\n"))
        lines.append(("class:muted", "↑↓ 选择 · Enter 确认 · Esc 退出\n\n"))
        for i, (_, label) in enumerate(items, start=1):
            if (i - 1) == state["index"]:
                lines.append(("class:selected", f"> {i}. {label}\n"))
            else:
                lines.append(("", f"  {i}. {label}\n"))
        return lines

    control = FormattedTextControl(
        text=_render,
        focusable=True,
        show_cursor=False,
    )
    root = Window(content=control, always_hide_cursor=True)
    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        state["index"] = max(0, state["index"] - 1)
        event.app.invalidate()

    @kb.add("down")
    def _down(event):
        state["index"] = min(len(items) - 1, state["index"] + 1)
        event.app.invalidate()

    @kb.add("enter")
    def _enter(event):
        event.app.exit(result=items[state["index"]][0])

    @kb.add("escape")
    def _esc(event):
        event.app.exit(result="quit")

    @kb.add("j")
    def _j(event):
        state["index"] = min(len(items) - 1, state["index"] + 1)
        event.app.invalidate()

    @kb.add("k")
    def _k(event):
        state["index"] = max(0, state["index"] - 1)
        event.app.invalidate()

    style = Style.from_dict(
        {
            "cwd": "bold",
            "muted": "fg:#888888",
            "selected": "bold",
        }
    )

    app = Application(
        layout=Layout(root),
        key_bindings=kb,
        style=style,
        full_screen=False,
    )
    result = app.run()
    return result or "quit"


def _input_tui(prompt_text: str, default: str = "") -> str:
    from prompt_toolkit import prompt

    try:
        text = prompt(f"{prompt_text}\n> ", default=default or "")
        return (text or "").strip()
    except (KeyboardInterrupt, EOFError):
        return ""


def _menu_plain(save_dir: str) -> str:
    print("\n当前下载路径:", save_dir)
    print("请选择操作：")
    print("  1. 登录 / 检查登录状态")
    print("  2. 开始批量爬取")
    print("  3. 重试失败项")
    print("  4. 配置下载路径")
    print("  q. 退出")
    print("请输入选项: ", end="", flush=True)
    choice = sys.stdin.readline().strip()

    if not choice:
        return ""
    if choice.lower() in ["q", "quit", "exit"]:
        return "quit"
    return {
        "1": "login",
        "2": "batch",
        "3": "retry_failed",
        "4": "set_path",
    }.get(choice, "invalid")


def _try_tui(
    use_tui_ref: list[bool],
    tui_func: Callable[[], T],
    plain_func: Callable[[], T],
    fallback_msg: str,
) -> T:
    if use_tui_ref[0]:
        try:
            return tui_func()
        except Exception as exc:
            print(f"提示：{fallback_msg}。原因：{exc}")
            use_tui_ref[0] = False
    return plain_func()


def _plain_input(prompt_text: str, prefix: str = "") -> str:
    print(f"{prefix}{prompt_text} ", end="", flush=True)
    return sys.stdin.readline().strip()


def _read_links_tui() -> list[str]:
    print("逐行粘贴链接或分享文本，空行结束；输入 @文件路径 可批量导入。")
    lines = []
    while True:
        line = _input_tui("链接/文本（空行结束）:")
        if not line:
            break
        lines.append(line)
    return lines


def _read_links_plain() -> list[str]:
    print("逐行粘贴链接或分享文本，空行结束；输入 @文件路径 可批量导入。")
    lines = []
    while True:
        line = sys.stdin.readline().strip()
        if not line:
            break
        lines.append(line)
    return lines


def _collect_urls(lines: list[str]) -> list[str]:
    urls: list[str] = []
    for index, line in enumerate(lines, start=1):
        if line.startswith("@"):
            path = Path(line[1:].strip()).expanduser()
            try:
                file_lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                print(f"第 {index} 行：无法读取文件 {path}: {exc}")
                continue
            for file_line in file_lines:
                url = extract_url_from_text(file_line)
                if url:
                    urls.append(url)
            continue

        url = extract_url_from_text(line)
        if url:
            urls.append(url)
        else:
            print(f"第 {index} 行未识别到链接，已跳过")
    return urls


def main() -> None:
    print("=" * 60)
    print("抖音视频爬虫命令行版 v1.1")
    print("功能：登录态复用、批量爬取、限频重试、断点续爬")
    use_tui = _tui_available()
    if use_tui:
        print("操作：↑↓ 选择，Enter 确认；Esc 退出。")
        print('提示：在"输入路径/链接"时，使用 Ctrl+C 取消并返回菜单。')
    else:
        print("操作：启动后选择功能。输入 'q' 退出。")
    print("=" * 60)

    config = load_config()
    config.save_dir.mkdir(parents=True, exist_ok=True)
    save_dir = str(config.save_dir)
    store = StateStore()
    store.load()
    session = BrowserSession(config)
    use_tui_ref = [use_tui]

    try:
        while True:
            try:
                action = _try_tui(
                    use_tui_ref,
                    lambda: _menu_tui(save_dir),
                    lambda: _menu_plain(save_dir),
                    "交互式菜单不可用，已回退到数字菜单",
                )

                if not action:
                    continue

                if action == "quit":
                    print("程序已退出。")
                    break

                if action == "invalid":
                    print("无效选项，请重新选择。")
                    continue

                if action == "login":
                    try:
                        session.start()
                    except RuntimeError as exc:
                        print(exc)
                        continue
                    if session.ensure_login(
                        lambda message: print(message)
                    ):
                        print("登录状态：已登录")
                    else:
                        print(
                            "未检测到登录态。请使用有头模式并重新执行登录。"
                        )
                    continue

                if action == "set_path":
                    new_dir = _try_tui(
                        use_tui_ref,
                        lambda: _input_tui(
                            "请输入下载路径（留空则不修改）:",
                            default=save_dir,
                        ),
                        lambda: _plain_input(
                            "请输入下载路径(留空则不修改):"
                        ),
                        "交互式输入不可用，已回退到普通输入",
                    )

                    if not new_dir:
                        print("下载路径未修改。")
                        continue

                    config.save_dir = Path(new_dir).expanduser().resolve()
                    config.save_dir.mkdir(parents=True, exist_ok=True)
                    save_config(config)
                    save_dir = str(config.save_dir)
                    print("下载路径已设置为:", save_dir)
                    continue

                if action in ("batch", "retry_failed"):
                    if action == "retry_failed":
                        urls = store.failed_urls()
                        if not urls:
                            print("没有失败项。")
                            continue
                    else:
                        lines = _try_tui(
                            use_tui_ref,
                            _read_links_tui,
                            _read_links_plain,
                            "交互式输入不可用，已回退到普通输入",
                        )
                        urls = _collect_urls(lines)
                        if not urls:
                            print("未识别到有效链接。")
                            continue

                    try:
                        session.start()
                    except RuntimeError as exc:
                        print(exc)
                        continue
                    if not session.is_logged_in():
                        print(
                            "警告：未检测到登录态，可能触发验证；"
                            "建议先执行「登录」。"
                        )

                    runner = BatchRunner(session, config, store)
                    summary = runner.run(
                        urls,
                        retry_failed=(action == "retry_failed"),
                    )
                    print(
                        f"完成：共 {summary.total}，成功 {summary.success}，"
                        f"跳过 {summary.skipped}，失败 {summary.failed}"
                    )
                    if summary.failed_urls:
                        print("失败链接：")
                        for url in summary.failed_urls:
                            print(" -", url)
                    continue

            except KeyboardInterrupt:
                print("\n程序已退出")
                break
            except Exception as exc:
                print(f"发生未预期的错误: {exc}")
                traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行 CLI 测试并做导入检查**

Run:
```bash
.venv/Scripts/python.exe -m pytest test_cli.py -q
.venv/Scripts/python.exe -c "import cli; print('cli import ok')"
```

Expected: `3 passed`，并输出 `cli import ok`。

- [ ] **Step 5: 提交**

```bash
git add cli.py test_cli.py
git commit -m "feat: CLI 增加登录、批量与失败重试入口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: 反爬脚本加固

**Files:**
- Modify: `stealth.min.js`

- [ ] **Step 1: 替换 `stealth.min.js` 内容**

```javascript
// playwright stealth evasions (minimal)
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en'],
});

Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
});

Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
});

Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
});

const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) {
        return 'Intel Inc.';
    }
    if (parameter === 37446) {
        return 'Intel Iris OpenGL Engine';
    }
    return getParameter(parameter);
};

window.chrome = window.chrome || { runtime: {} };

const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: 'denied' })
        : originalQuery(parameters)
);

const iframeContentWindow = Object.getOwnPropertyDescriptor(
    HTMLIFrameElement.prototype,
    'contentWindow'
);
if (iframeContentWindow && iframeContentWindow.get) {
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() {
            const result = iframeContentWindow.get.call(this);
            if (result) {
                result.chrome = result.chrome || { runtime: {} };
            }
            return result;
        }
    });
}
```

- [ ] **Step 2: 语法检查（安装了 Node.js 时）**

Run:
```bash
node --check stealth.min.js
```

Expected: 无输出，退出码 0。若本机没有 Node.js，跳过此步，人工确认文件内容与上面一致。

- [ ] **Step 3: 提交**

```bash
git add stealth.min.js
git commit -m "chore: 加固浏览器指纹脚本

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 文档、版本提示与最终验证

**Files:**
- Rewrite: `README.md`
- Modify: `setup.cmd`

- [ ] **Step 1: 更新 `setup.cmd` 的 Python 版本提示**

把：

```text
echo [ERROR] 未找到 python，请先安装 Python 3.8+ 并加入 PATH。
```

改为：

```text
echo [ERROR] 未找到 python，请先安装 Python 3.10+ 并加入 PATH。
```

- [ ] **Step 2: 重写 `README.md`**

````markdown
# Douyin Video Downloader (抖音视频下载器)

基于 Python Playwright 的抖音视频下载工具（命令行版），支持登录态复用、批量爬取、限频与断点续爬。

## 功能特点

- 自动提取分享文本中的链接
- 持久化登录态：首次扫码，之后复用浏览器 profile
- 批量多链接：逐行粘贴或从文件导入
- 两级限频：页面访问与媒体下载分别控制间隔
- 下载重试与断点续传：`.part` 文件 + HTTP Range
- 断点续爬与去重：`state.json` 记录状态，可按作品 ID 去重
- 风控识别：登录失效、验证码、无视频时给出明确提示
- 反爬加固：stealth 脚本、环境一致性、轻量行为模拟

## 环境要求

- Python 3.10+
- Windows / macOS / Linux 桌面环境
- 首次登录需要可用的图形界面

## 安装

```bash
git clone https://github.com/yyyCode/spider.git
cd spider
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Windows 一键安装：

```powershell
.\setup.cmd
```

## 运行

```bash
.\run.cmd
```

或：

```bash
python cli.py
```

菜单：

1. 登录 / 检查登录状态
2. 开始批量爬取
3. 重试失败项
4. 配置下载路径
5. 退出

## 登录

首次使用请选择「登录 / 检查登录状态」，浏览器会打开抖音首页。扫码登录成功后，程序会自动保存登录态。profile 位于 `~/.douyin-spider/profile`。

注意：

- 同一时间只能有一个程序使用该 profile。
- 默认有头模式；无头模式无法完成首次扫码。
- 登录失效时重新执行登录即可。

## 批量爬取

选择「开始批量爬取」后：

- 逐行粘贴分享文本或链接，输入空行结束；
- 输入 `@文件路径` 可从文本文件导入，每行一个链接；
- 程序会按输入顺序串行处理，并显示进度。

状态文件位于 `~/.douyin-spider/state.json`。再次运行时已成功的条目会跳过；失败项可通过「重试失败项」重新处理。

## 配置

配置文件位于 `~/.douyin-spider/config.json`，首次运行自动生成。常用字段：

| 字段 | 默认值 | 说明 |
|---|---|---|
| save_dir | `<cwd>/videos` | 下载目录 |
| headless | false | 是否无头运行；首次登录必须为 false |
| page_delay | [4.0, 9.0] | 页面访问间隔范围（秒） |
| download_delay | [1.0, 2.0] | 下载间隔范围（秒） |
| cooldown_seconds | 90 | 触发 429/风控后的冷却时间 |
| max_retries | 3 | 下载最大尝试次数 |
| page_timeout_ms | 60000 | 页面加载超时 |
| video_wait_timeout_ms | 15000 | 等待视频元素超时 |
| login_timeout_seconds | 180 | 等待扫码登录的超时 |
| min_video_size | 1048576 | 过滤小文件（广告） |
| chunk_size | 65536 | 下载分块大小 |
| human_behavior | true | 是否启用轻量行为模拟 |

## 常见问题

- **提示需要登录 / 触发验证**：执行「登录」并使用有头模式手动完成验证。
- **浏览器启动失败**：关闭其他使用同一 profile 的程序后重试。
- **下载 403**：直链过期，程序会自动重新嗅探；多次失败可重试该链接。
- **没有捕获到视频**：页面可能改版或需要登录，先检查登录态，再重试。

## 合规说明

本工具仅用于个人学习与研究。请遵守抖音平台条款、robots 协议及当地法律法规，控制访问频率，不要用于批量抓取或商业用途。

## License

MIT
````

- [ ] **Step 3: 运行完整测试**

Run:
```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: 全部测试通过，无 `failed` 或 `error`。

- [ ] **Step 4: 检查模块导入**

Run:
```bash
.venv/Scripts/python.exe -c "import cli, batch, config, downloader, rate_limiter, session, douyin_spider; print('all imports ok')"
```

Expected: 输出 `all imports ok`。

- [ ] **Step 5: 检查工作区只包含预期改动**

Run:
```bash
git status --short
```

Expected: 只显示本计划修改或新增的文件；`draw/455.png` 和 `.codewhale/` 仍未暂存。

- [ ] **Step 6: 提交**

```bash
git add README.md setup.cmd
git commit -m "docs: 更新登录、批量与配置说明

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完成标准

- `pytest -q` 全部通过。
- 首次运行 `python cli.py` 能生成 `~/.douyin-spider/config.json`，并能进入登录菜单。
- 登录一次后重启程序，`session.is_logged_in()` 为真，无需重复扫码。
- 批量输入 3 条链接时逐条处理，条目间有随机间隔；中途退出后重跑会跳过成功项。
- 遇到 403 时会重新嗅探直链；下载中断后 `.part` 文件可被续传。
- 触发登录/验证码时，有头模式提示人工处理，无头模式给出明确失败原因。
