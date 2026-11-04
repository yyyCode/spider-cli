# FastAPI Web 下载服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有抖音/小红书爬虫增加一个 FastAPI Web 前端：粘贴链接后同步返回视频文件，并提供暗色玻璃拟态 UI。

**Architecture:** 新增 `web/` 包，复用 `core/` 的平台下载逻辑。`web/service.py` 负责链接提取、平台识别、临时目录与爬虫调用；`web/app.py` 提供 `POST /api/download`、`GET /`、`GET /health`；`web/static/` 存放单页前端。core 只做最小改造：两个爬虫的 `run()` 成功时返回下载路径，小红书新增 `resolve()` 用于提前判断笔记类型。

**Tech Stack:** Python 3.8+、FastAPI、Uvicorn、Starlette FileResponse/BackgroundTask、Playwright、requests、原生 HTML/CSS/JS。

---

## 文件结构

```text
web/
├── __init__.py        # 包说明
├── __main__.py        # python -m web 启动入口，解析 --host/--port/--reload
├── app.py             # FastAPI 应用、路由、静态资源、并发信号量
├── service.py         # 下载编排、错误映射、临时目录管理
└── static/
    ├── index.html
    ├── styles.css
    └── app.js

tests/
├── test_web_service.py  # 编排层单元测试（不依赖 FastAPI）
└── test_web_app.py      # FastAPI 端点测试
```

修改：`core/douyin_spider.py`、`core/xhs_spider.py`、`requirements.txt`、`README.md`。
新增：`run-web.cmd`。

---

### Task 1: 安装 Web 依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 在 requirements.txt 末尾追加依赖**

修改后的 `requirements.txt` 完整内容：

```text
playwright
requests
prompt_toolkit
fastapi
uvicorn[standard]
```

- [ ] **Step 2: 安装依赖**

Run:

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Windows CMD 等价命令：`.venv\Scripts\python.exe -m pip install -r requirements.txt`

Expected: 输出 `Successfully installed ... fastapi ... uvicorn ...`，无报错。

- [ ] **Step 3: 验证导入**

Run:

```bash
./.venv/Scripts/python.exe -c "import fastapi, uvicorn, starlette; print(fastapi.__version__, uvicorn.__version__)"
```

Expected: 打印两个版本号。

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: 添加 FastAPI 与 Uvicorn 依赖

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 抖音爬虫返回下载路径

**Files:**
- Modify: `core/douyin_spider.py:172-201`（`download_video` 与 `run` 结尾）
- Test: `tests/test_douyin.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_douyin.py` 末尾追加：

```python
class _FakeDownloadResponse:
    status_code = 200

    def iter_content(self, chunk_size=8192):
        yield b"fake-video-bytes"


class _ForbiddenResponse:
    status_code = 403

    def iter_content(self, chunk_size=8192):
        yield b""


class TestDouyinDownload:
    def test_download_video_returns_path(self, monkeypatch, tmp_path):
        spider = DouyinSpider("https://example.com", save_dir=str(tmp_path))
        monkeypatch.setattr(
            "core.douyin_spider.requests.get",
            lambda *args, **kwargs: _FakeDownloadResponse(),
        )
        target = tmp_path / "video.mp4"

        result = spider.download_video("https://cdn.example.com/x.mp4", str(target))

        assert result == str(target)
        assert target.read_bytes() == b"fake-video-bytes"

    def test_download_video_returns_none_on_http_error(self, monkeypatch, tmp_path):
        spider = DouyinSpider("https://example.com", save_dir=str(tmp_path))
        monkeypatch.setattr(
            "core.douyin_spider.requests.get",
            lambda *args, **kwargs: _ForbiddenResponse(),
        )
        target = tmp_path / "x.mp4"

        result = spider.download_video("https://cdn.example.com/x.mp4", str(target))

        assert result is None
        assert not target.exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_douyin.py::TestDouyinDownload -v
```

Expected: 两个测试 FAIL，`test_download_video_returns_path` 断言 `None == path` 失败。

- [ ] **Step 3: 修改 download_video 返回路径**

把 `core/douyin_spider.py` 中的 `download_video` 完整替换为：

```python
    def download_video(self, url, filepath):
        self.log(f"开始下载: {filepath}")
        try:
            # 抖音视频链接通常需要带上 headers 避免 403
            response = requests.get(url, headers=self.headers, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                self.log(f"下载完成！文件已保存至: {filepath}")
                return filepath
            self.log(f"下载失败，状态码: {response.status_code}")
        except Exception as e:
            self.log(f"下载出错: {e}")
        return None
```

- [ ] **Step 4: 修改 run 返回下载结果**

把 `core/douyin_spider.py` 中 `run()` 的下载分支替换为：

```python
            result = None
            if target_url:
                filename = f"{title}.mp4"
                filepath = os.path.join(self.save_dir, filename)
                result = self.download_video(target_url, filepath)
            else:
                self.log("未能获取到视频链接。可能原因：")
                self.log("1. 视频是 blob 格式（加密流），当前爬虫暂不支持")
                self.log("2. 反爬虫检测拦截了请求")
                self.log("3. 需要登录")

            browser.close()
            return result
```

注意保留原来的 `browser.close()`，并确保 `return result` 是 `run()` 最后一行。浏览器启动失败时的 `return` 保持原样（返回 `None`）。

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_douyin.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add core/douyin_spider.py tests/test_douyin.py
git commit -m "feat: 抖音爬虫返回下载文件路径

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 小红书爬虫新增 resolve 并返回路径

**Files:**
- Modify: `core/xhs_spider.py:248-305`（`run`、`download_note`、`_download_video`）
- Test: `tests/test_xhs.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_xhs.py` 的导入列表中加入 `NoteMedia`：

```python
from core.xhs_spider import (
    NoteMedia,
    XhsError,
    XhsSpider,
    extract_note_id,
    parse_initial_state,
    parse_note,
    parse_setup_state,
)
```

在文件末尾追加：

```python
class TestXhsDownloadResults:
    def test_resolve_returns_media(self, monkeypatch):
        spider = XhsSpider("https://www.xiaohongshu.com/explore/abc")
        media = NoteMedia(
            note_id="n1", title="标题", kind="video", video_urls=["http://v/1.mp4"]
        )
        monkeypatch.setattr(spider, "fetch_html", lambda: ("https://final", "<html>"))
        monkeypatch.setattr(spider, "parse", lambda final_url, html: media)

        assert spider.resolve() is media

    def test_download_note_video_returns_path(self, tmp_path, monkeypatch):
        spider = XhsSpider(
            "https://www.xiaohongshu.com/explore/abc", save_dir=str(tmp_path)
        )
        media = NoteMedia(
            note_id="n1", title="测试视频", kind="video", video_urls=["http://v/1.mp4"]
        )
        monkeypatch.setattr(spider, "_download_file", lambda *args, **kwargs: True)

        result = spider.download_note(media)

        assert result == str(tmp_path / "测试视频" / "测试视频.mp4")

    def test_download_note_video_returns_none_when_all_fail(self, tmp_path, monkeypatch):
        spider = XhsSpider(
            "https://www.xiaohongshu.com/explore/abc", save_dir=str(tmp_path)
        )
        media = NoteMedia(
            note_id="n1", title="测试视频", kind="video", video_urls=["http://v/1.mp4"]
        )
        monkeypatch.setattr(spider, "_download_file", lambda *args, **kwargs: False)

        assert spider.download_note(media) is None

    def test_download_note_images_returns_dir(self, tmp_path, monkeypatch):
        spider = XhsSpider(
            "https://www.xiaohongshu.com/explore/abc", save_dir=str(tmp_path)
        )
        media = NoteMedia(
            note_id="n1",
            title="图集",
            kind="images",
            image_urls=[["http://img/1.jpg"]],
        )
        monkeypatch.setattr(spider, "_download_images", lambda media, out_dir: True)

        assert spider.download_note(media) == str(tmp_path / "图集")

    def test_download_note_images_returns_none_on_failure(self, tmp_path, monkeypatch):
        spider = XhsSpider(
            "https://www.xiaohongshu.com/explore/abc", save_dir=str(tmp_path)
        )
        media = NoteMedia(
            note_id="n1",
            title="图集",
            kind="images",
            image_urls=[["http://img/1.jpg"]],
        )
        monkeypatch.setattr(spider, "_download_images", lambda media, out_dir: False)

        assert spider.download_note(media) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_xhs.py::TestXhsDownloadResults -v
```

Expected: FAIL，`XhsSpider` 没有 `resolve` 属性，或返回值不是路径。

- [ ] **Step 3: 新增 resolve 并修改 run**

把 `core/xhs_spider.py` 中的 `run` 完整替换为：

```python
    def resolve(self):
        """抓取并解析笔记，返回 NoteMedia；失败抛出 XhsError。"""
        final_url, html = self.fetch_html()
        return self.parse(final_url, html)

    def run(self):
        try:
            media = self.resolve()
            self.log(f"笔记: {media.title}（{'视频' if media.kind == 'video' else '图集'}）")
            return self.download_note(media)
        except XhsError as exc:
            self.log(f"失败: {exc}")
            return None
        except requests.RequestException as exc:
            self.log(f"网络请求失败: {exc}")
            return None
        except OSError as exc:
            self.log(f"文件写入失败: {exc}")
            return None
```

- [ ] **Step 4: 修改 download_note 返回路径**

把 `download_note` 完整替换为：

```python
    def download_note(self, media):
        out_dir = os.path.join(self.save_dir, media.title)
        os.makedirs(out_dir, exist_ok=True)
        if media.kind == "video":
            return self._download_video(media, out_dir)
        if self._download_images(media, out_dir):
            return out_dir
        return None
```

- [ ] **Step 5: 修改 _download_video 返回路径**

把 `_download_video` 完整替换为：

```python
    def _download_video(self, media, out_dir):
        if not media.video_urls:
            self.log("未找到视频地址，可能是动图或受限内容")
            return None

        filepath = os.path.join(out_dir, f"{media.title}.mp4")
        if self._is_complete(filepath):
            self.log(f"已存在，跳过: {filepath}")
            return filepath

        for url in media.video_urls:
            if self._download_file(url, filepath, expect="video"):
                self.log(f"下载完成: {filepath}")
                return filepath
        self.log("视频下载失败: 所有候选地址均不可用")
        return None
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_xhs.py -v
```

Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add core/xhs_spider.py tests/test_xhs.py
git commit -m "feat: 小红书爬虫新增 resolve 并返回下载路径

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Web 下载编排服务

**Files:**
- Create: `web/__init__.py`
- Create: `web/service.py`
- Test: `tests/test_web_service.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_web_service.py`：

```python
"""Tests for the web download orchestration."""

import shutil
from pathlib import Path

import pytest

from core.xhs_spider import NoteMedia
from web import service


class FakeDouyinSpider:
    def __init__(self, save_dir):
        self.save_dir = save_dir

    def run(self):
        target = Path(self.save_dir) / "抖音视频.mp4"
        target.write_bytes(b"douyin-bytes")
        return str(target)


class FakeXhsSpider:
    def __init__(self, media, save_dir):
        self.media = media
        self.save_dir = save_dir

    def resolve(self):
        return self.media

    def download_note(self, media):
        target = Path(self.save_dir) / f"{media.title}.mp4"
        target.write_bytes(b"xhs-bytes")
        return str(target)


class FakeFailingSpider:
    def run(self):
        return None


def test_download_video_douyin_success(monkeypatch):
    monkeypatch.setattr(
        service,
        "create_spider",
        lambda platform, url, save_dir, log: FakeDouyinSpider(save_dir),
    )

    result = service.download_video("复制口令 https://v.douyin.com/abc/ 打开")

    try:
        assert result.filename == "抖音视频.mp4"
        assert Path(result.path).read_bytes() == b"douyin-bytes"
    finally:
        shutil.rmtree(result.temp_dir, ignore_errors=True)


def test_download_video_xhs_video_success(monkeypatch):
    media = NoteMedia(
        note_id="n", title="小红书视频", kind="video", video_urls=["http://v"]
    )
    monkeypatch.setattr(
        service,
        "create_spider",
        lambda platform, url, save_dir, log: FakeXhsSpider(media, save_dir),
    )

    result = service.download_video("https://www.xiaohongshu.com/explore/abc")

    try:
        assert result.filename == "小红书视频.mp4"
        assert Path(result.path).read_bytes() == b"xhs-bytes"
    finally:
        shutil.rmtree(result.temp_dir, ignore_errors=True)


def test_download_video_rejects_xhs_images(monkeypatch):
    media = NoteMedia(
        note_id="n",
        title="图集",
        kind="images",
        image_urls=[["http://img"]],
    )
    monkeypatch.setattr(
        service,
        "create_spider",
        lambda platform, url, save_dir, log: FakeXhsSpider(media, save_dir),
    )

    with pytest.raises(service.WebDownloadError) as excinfo:
        service.download_video("https://www.xiaohongshu.com/explore/abc")

    assert excinfo.value.status_code == 400
    assert "图集" in excinfo.value.message


def test_download_video_invalid_input():
    with pytest.raises(service.WebDownloadError) as excinfo:
        service.download_video("这里没有任何链接")

    assert excinfo.value.status_code == 400


def test_download_video_unsupported_platform():
    with pytest.raises(service.WebDownloadError) as excinfo:
        service.download_video("https://example.com/video/1")

    assert excinfo.value.status_code == 400


def test_download_video_spider_failure(monkeypatch):
    monkeypatch.setattr(
        service,
        "create_spider",
        lambda platform, url, save_dir, log: FakeFailingSpider(),
    )

    with pytest.raises(service.WebDownloadError) as excinfo:
        service.download_video("https://v.douyin.com/abc/")

    assert excinfo.value.status_code == 502


def test_failure_cleans_temp_dir(monkeypatch, tmp_path):
    created = tmp_path / "tmp-download"
    created.mkdir()
    monkeypatch.setattr(service.tempfile, "mkdtemp", lambda prefix="": str(created))
    monkeypatch.setattr(
        service,
        "create_spider",
        lambda platform, url, save_dir, log: FakeFailingSpider(),
    )

    with pytest.raises(service.WebDownloadError):
        service.download_video("https://v.douyin.com/abc/")

    assert not created.exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_web_service.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'web'`。

- [ ] **Step 3: 创建包入口**

创建 `web/__init__.py`：

```python
"""FastAPI web frontend for the spider CLI."""
```

- [ ] **Step 4: 创建 service.py**

创建 `web/service.py`：

```python
"""Orchestrate platform downloads for the web frontend."""

import os
import shutil
import tempfile
from dataclasses import dataclass

from core.douyin_spider import DouyinSpider
from core.utils import detect_platform, extract_url_from_text
from core.xhs_spider import XhsSpider


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


def create_spider(platform, url, save_dir, log_callback):
    """按平台创建爬虫；单独抽出便于测试替换。"""
    if platform == "douyin":
        return DouyinSpider(url, save_dir=save_dir, log_callback=log_callback)
    return XhsSpider(
        url,
        save_dir=save_dir,
        cookie=os.environ.get("XHS_COOKIE"),
        log_callback=log_callback,
    )


def _resolve_input(raw_url):
    url = extract_url_from_text((raw_url or "").strip())
    if not url:
        raise WebDownloadError("未识别到有效链接，请粘贴完整的分享口令或 URL", 400)
    platform = detect_platform(url)
    if platform not in {"douyin", "xhs"}:
        raise WebDownloadError("仅支持抖音和小红书链接", 400)
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


def download_video(raw_url):
    """同步执行一次视频下载，文件保存在本次请求的临时目录中。"""
    url, platform = _resolve_input(raw_url)
    temp_dir = tempfile.mkdtemp(prefix="spider-web-")
    logs = []

    try:
        spider = create_spider(platform, url, temp_dir, logs.append)
        if platform == "douyin":
            path = _download_douyin(spider, logs)
        else:
            path = _download_xhs(spider, logs)

        if not path or not os.path.isfile(path):
            raise WebDownloadError(
                _failure_detail(logs, "未能获取到视频文件，可能链接失效或内容受限"),
                502,
            )

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
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_web_service.py -v
```

Expected: 7 个测试全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add web/__init__.py web/service.py tests/test_web_service.py
git commit -m "feat: 新增 Web 下载编排服务

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 静态前端页面

**Files:**
- Create: `web/static/index.html`
- Create: `web/static/styles.css`
- Create: `web/static/app.js`

本任务只创建静态文件，不做自动化测试；界面行为在 Task 8 手动验证。

- [ ] **Step 1: 创建 index.html**

创建 `web/static/index.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Spider CLI · 视频下载</title>
  <link rel="icon" href="/assets/logo-128.png">
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <div class="aurora aurora--one"></div>
  <div class="aurora aurora--two"></div>
  <div class="aurora aurora--three"></div>

  <main class="shell">
    <section class="card">
      <header class="card__header">
        <img class="logo" src="/assets/logo.png" alt="Spider CLI logo">
        <div>
          <h1>视频下载器</h1>
          <p class="subtitle">粘贴抖音或小红书链接，直接下载视频文件</p>
        </div>
      </header>

      <form id="download-form" class="form" autocomplete="off">
        <label class="field">
          <span class="field__label">链接或分享口令</span>
          <textarea id="url-input" rows="3"
            placeholder="例如：7.43 复制打开抖音，看看... https://v.douyin.com/xxxx/"
            spellcheck="false"></textarea>
        </label>

        <div class="meta">
          <span id="platform-badge" class="badge badge--idle">等待输入</span>
          <span class="hint">Ctrl + Enter 快速提交</span>
        </div>

        <button id="submit-btn" type="submit" class="button" disabled>
          <span class="button__label">解析并下载</span>
          <span class="spinner" aria-hidden="true"></span>
        </button>
      </form>

      <section id="status" class="status" hidden>
        <div class="status__row">
          <p id="status-text" class="status__text"></p>
          <span id="status-percent" class="status__percent"></span>
        </div>
        <div class="progress" id="progress" hidden>
          <div id="progress-bar" class="progress__bar"></div>
        </div>
      </section>

      <p class="footnote">当前仅支持视频；小红书图集暂不支持。抖音解析可能需要 10–30 秒。</p>
    </section>
  </main>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 创建 styles.css**

创建 `web/static/styles.css`：

```css
:root {
  --card-bg: rgba(16, 22, 44, 0.58);
  --card-border: rgba(255, 255, 255, 0.14);
  --text: #eef2ff;
  --muted: #96a2c4;
  --accent: #6d8cff;
  --success: #43e0a4;
  --danger: #ff7185;
  --radius-xl: 26px;
  --radius-md: 14px;
  --shadow: 0 30px 80px rgba(0, 0, 0, 0.55);
  --font: "Inter", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
}

* { box-sizing: border-box; }

html, body { min-height: 100%; }

body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 40px 20px;
  color: var(--text);
  font-family: var(--font);
  background:
    radial-gradient(1100px 720px at 12% -10%, rgba(78, 96, 255, 0.3), transparent 62%),
    radial-gradient(900px 620px at 92% 8%, rgba(180, 92, 255, 0.22), transparent 58%),
    linear-gradient(155deg, #05070f 0%, #090e21 48%, #120a26 100%);
  overflow-x: hidden;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  background-image: radial-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: radial-gradient(circle at 50% 30%, black, transparent 72%);
  pointer-events: none;
}

.aurora {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.5;
  pointer-events: none;
  animation: float 18s ease-in-out infinite alternate;
}

.aurora--one { width: 420px; height: 420px; top: -120px; left: -80px; background: #3d5bff; }
.aurora--two { width: 380px; height: 380px; bottom: -140px; right: -60px; background: #a44dff; animation-delay: -6s; }
.aurora--three { width: 260px; height: 260px; top: 40%; right: 18%; background: #14e0c8; opacity: 0.25; animation-delay: -12s; }

@keyframes float {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(30px, -40px, 0) scale(1.12); }
}

.shell { width: min(640px, 100%); position: relative; z-index: 1; }

.card {
  position: relative;
  padding: 36px;
  border-radius: var(--radius-xl);
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
}

.card::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(130deg, rgba(255, 255, 255, 0.1), transparent 36%);
  pointer-events: none;
}

.card__header { display: flex; align-items: center; gap: 18px; margin-bottom: 28px; }

.logo {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  box-shadow: 0 12px 30px rgba(109, 140, 255, 0.35);
}

h1 { margin: 0 0 6px; font-size: 26px; letter-spacing: -0.02em; }

.subtitle { margin: 0; color: var(--muted); font-size: 14px; }

.form { display: grid; gap: 16px; }

.field { display: grid; gap: 8px; }

.field__label { font-size: 13px; color: var(--muted); letter-spacing: 0.02em; }

textarea {
  width: 100%;
  min-height: 104px;
  resize: vertical;
  padding: 16px 18px;
  color: var(--text);
  font: inherit;
  font-size: 15px;
  line-height: 1.6;
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(6, 10, 24, 0.55);
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

textarea::placeholder { color: rgba(150, 162, 196, 0.55); }

textarea:focus {
  border-color: rgba(125, 148, 255, 0.75);
  box-shadow: 0 0 0 4px rgba(109, 140, 255, 0.16);
  background: rgba(8, 12, 28, 0.7);
}

.meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; }

.hint { font-size: 12px; color: rgba(150, 162, 196, 0.7); }

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  border: 1px solid transparent;
  transition: all 0.2s;
}

.badge::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 10px currentColor;
}

.badge--idle { color: var(--muted); background: rgba(255, 255, 255, 0.05); border-color: rgba(255, 255, 255, 0.08); }
.badge--douyin { color: #7ee7ff; background: rgba(20, 224, 200, 0.1); border-color: rgba(20, 224, 200, 0.35); }
.badge--xhs { color: #ff9bb0; background: rgba(255, 77, 109, 0.12); border-color: rgba(255, 77, 109, 0.38); }

.button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 15px 22px;
  border: none;
  border-radius: var(--radius-md);
  font: inherit;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #fff;
  cursor: pointer;
  background: linear-gradient(120deg, #5b76ff 0%, #9a5bff 55%, #d24dff 100%);
  box-shadow: 0 14px 36px rgba(112, 92, 255, 0.38), inset 0 1px 0 rgba(255, 255, 255, 0.25);
  transition: transform 0.18s, box-shadow 0.18s, filter 0.18s;
}

.button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 18px 42px rgba(112, 92, 255, 0.5);
  filter: brightness(1.06);
}

.button:active:not(:disabled) { transform: translateY(0); }

.button:disabled { cursor: not-allowed; filter: saturate(0.3) brightness(0.7); box-shadow: none; }

.spinner {
  display: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}

.button.is-loading .spinner { display: inline-block; }

@keyframes spin { to { transform: rotate(360deg); } }

.status {
  margin-top: 22px;
  padding: 16px 18px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(6, 10, 24, 0.45);
}

.status[hidden] { display: none; }

.status__row { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }

.status__text { margin: 0; font-size: 14px; line-height: 1.5; }

.status__percent { font-size: 13px; color: var(--muted); white-space: nowrap; }

.status--success { border-color: rgba(67, 224, 164, 0.45); background: rgba(67, 224, 164, 0.08); }
.status--success .status__text { color: var(--success); }

.status--error { border-color: rgba(255, 113, 133, 0.5); background: rgba(255, 113, 133, 0.09); }
.status--error .status__text { color: var(--danger); }

.progress {
  margin-top: 12px;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
}

.progress[hidden] { display: none; }

.progress__bar {
  width: 0;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #5b76ff, #b15bff);
  box-shadow: 0 0 16px rgba(140, 100, 255, 0.7);
  transition: width 0.2s ease;
}

.footnote { margin: 22px 0 0; font-size: 12px; line-height: 1.7; color: rgba(150, 162, 196, 0.65); }

@media (max-width: 560px) {
  body { padding: 24px 14px; }
  .card { padding: 26px 20px; border-radius: 22px; }
  .card__header { gap: 14px; }
  .logo { width: 46px; height: 46px; }
  h1 { font-size: 22px; }
  .hint { display: none; }
}
```

- [ ] **Step 3: 创建 app.js**

创建 `web/static/app.js`：

```javascript
const form = document.getElementById("download-form");
const input = document.getElementById("url-input");
const button = document.getElementById("submit-btn");
const buttonLabel = button.querySelector(".button__label");
const badge = document.getElementById("platform-badge");
const statusBox = document.getElementById("status");
const statusText = document.getElementById("status-text");
const statusPercent = document.getElementById("status-percent");
const progress = document.getElementById("progress");
const progressBar = document.getElementById("progress-bar");

const URL_RE = /https?:\/\/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+/;
const PLATFORM_HOSTS = {
  douyin: [/(^|\.)douyin\.com$/i, /(^|\.)iesdouyin\.com$/i],
  xhs: [/(^|\.)xiaohongshu\.com$/i, /(^|\.)xhslink\.com$/i],
};
const PENDING_MESSAGES = ["正在解析链接…", "正在启动浏览器…", "正在下载视频…"];

let busy = false;

function detectPlatform(text) {
  const match = text.match(URL_RE);
  if (!match) return null;
  try {
    const host = new URL(match[0]).hostname.toLowerCase();
    for (const [platform, patterns] of Object.entries(PLATFORM_HOSTS)) {
      if (patterns.some((pattern) => pattern.test(host))) return platform;
    }
  } catch (_) {
    return null;
  }
  return null;
}

function updateBadge() {
  const platform = detectPlatform(input.value);
  badge.className = "badge";
  if (platform === "douyin") {
    badge.textContent = "抖音视频";
    badge.classList.add("badge--douyin");
  } else if (platform === "xhs") {
    badge.textContent = "小红书视频";
    badge.classList.add("badge--xhs");
  } else {
    badge.textContent = input.value.trim() ? "未识别到支持的链接" : "等待输入";
    badge.classList.add("badge--idle");
  }
  button.disabled = busy || !platform;
}

function setLoading(loading) {
  button.classList.toggle("is-loading", loading);
  buttonLabel.textContent = loading ? "处理中…" : "解析并下载";
  busy = loading;
  updateBadge();
}

function showStatus(kind, text, percent = "") {
  statusBox.hidden = false;
  statusBox.className = `status status--${kind}`;
  statusText.textContent = text;
  statusPercent.textContent = percent;
}

function setProgress(percent) {
  progress.hidden = false;
  progressBar.style.width = `${percent}%`;
}

function resetStatus() {
  statusBox.hidden = true;
  statusBox.className = "status";
  statusPercent.textContent = "";
  progress.hidden = true;
  progressBar.style.width = "0%";
}

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function parseFilename(header) {
  if (!header) return null;
  const encoded = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch (_) {
      /* 继续尝试普通 filename */
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1].trim() : null;
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function download(rawUrl) {
  setLoading(true);
  resetStatus();
  showStatus("processing", PENDING_MESSAGES[0]);
  setProgress(6);

  let messageIndex = 0;
  let receiving = false;
  const messageTimer = setInterval(() => {
    if (receiving) return;
    messageIndex = Math.min(messageIndex + 1, PENDING_MESSAGES.length - 1);
    showStatus("processing", PENDING_MESSAGES[messageIndex]);
  }, 4000);

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: rawUrl }),
    });

    if (!response.ok) {
      let detail = `请求失败（${response.status}）`;
      try {
        const data = await response.json();
        if (data && data.detail) detail = data.detail;
      } catch (_) {
        /* 保留默认错误文案 */
      }
      throw new Error(detail);
    }

    const filename = parseFilename(response.headers.get("Content-Disposition")) || "video.mp4";
    const total = Number(response.headers.get("Content-Length")) || 0;
    const contentType = response.headers.get("Content-Type") || "video/mp4";

    receiving = true;
    const reader = response.body.getReader();
    const chunks = [];
    let received = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      if (total) {
        const percent = Math.min(100, Math.round((received / total) * 100));
        setProgress(percent);
        showStatus("processing", "正在接收视频…", `${percent}%`);
      } else {
        showStatus("processing", "正在接收视频…", formatSize(received));
      }
    }

    const blob = new Blob(chunks, { type: contentType });
    saveBlob(blob, filename);
    setProgress(100);
    showStatus("success", `下载完成 · ${filename}`, formatSize(blob.size));
  } catch (error) {
    showStatus("error", error.message || "下载失败，请稍后重试");
    progress.hidden = true;
  } finally {
    clearInterval(messageTimer);
    setLoading(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy || !detectPlatform(input.value)) return;
  download(input.value.trim());
});

input.addEventListener("input", updateBadge);

input.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    form.requestSubmit();
  }
});

updateBadge();
```

- [ ] **Step 4: Commit**

```bash
git add web/static/index.html web/static/styles.css web/static/app.js
git commit -m "feat: 新增暗色玻璃拟态 Web 界面

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: FastAPI 应用与启动入口

**Files:**
- Create: `web/app.py`
- Create: `web/__main__.py`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_web_app.py`：

```python
"""Tests for the FastAPI endpoints."""

from fastapi.testclient import TestClient

from web import app as web_app
from web.service import DownloadedFile


def make_client():
    return TestClient(web_app.app)


def test_health():
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_serves_html():
    with make_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "视频下载器" in response.text


def test_download_returns_file_and_cleans_temp(monkeypatch, tmp_path):
    temp_dir = tmp_path / "download"
    temp_dir.mkdir()
    target = temp_dir / "测试视频.mp4"
    target.write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(
        web_app,
        "download_video",
        lambda raw: DownloadedFile(
            path=str(target),
            filename=target.name,
            temp_dir=str(temp_dir),
        ),
    )

    with make_client() as client:
        response = client.post(
            "/api/download", json={"url": "https://v.douyin.com/abc/"}
        )

    assert response.status_code == 200
    assert response.content == b"fake-video-bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert "attachment" in response.headers["content-disposition"]
    assert "mp4" in response.headers["content-disposition"]
    assert not temp_dir.exists()


def test_download_invalid_url_returns_400():
    with make_client() as client:
        response = client.post("/api/download", json={"url": "这里没有链接"})

    assert response.status_code == 400
    assert "链接" in response.json()["detail"]


def test_download_unsupported_platform_returns_400():
    with make_client() as client:
        response = client.post(
            "/api/download", json={"url": "https://example.com/video"}
        )

    assert response.status_code == 400
    assert "抖音" in response.json()["detail"]


def test_download_missing_url_returns_422():
    with make_client() as client:
        response = client.post("/api/download", json={})

    assert response.status_code == 422


def test_download_error_maps_to_status(monkeypatch):
    def raise_error(raw):
        raise web_app.WebDownloadError("上游解析失败", 502)

    monkeypatch.setattr(web_app, "download_video", raise_error)

    with make_client() as client:
        response = client.post(
            "/api/download", json={"url": "https://v.douyin.com/abc/"}
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "上游解析失败"}
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_web_app.py -v
```

Expected: FAIL，`ModuleNotFoundError` 或 `web` 包没有 `app`。

- [ ] **Step 3: 创建 app.py**

创建 `web/app.py`：

```python
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
```

- [ ] **Step 4: 创建启动入口**

创建 `web/__main__.py`：

```python
"""Start the web frontend with ``python -m web``."""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="启动 Spider CLI Web 服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    args = parser.parse_args()

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_web_app.py -v
```

Expected: 7 个测试全部 PASS。若 `test_download_returns_file_and_cleans_temp` 因后台任务时序失败，把该测试改成 `with make_client() as client:` 外层并保持原断言；不要删除清理断言。

- [ ] **Step 6: Commit**

```bash
git add web/app.py web/__main__.py tests/test_web_app.py
git commit -m "feat: 新增 FastAPI 下载端点与启动入口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Windows 启动脚本与 README

**Files:**
- Create: `run-web.cmd`
- Modify: `README.md`

- [ ] **Step 1: 创建 run-web.cmd**

创建 `run-web.cmd`：

```bat
@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PY_EXE%" (
  echo [ERROR] 未找到虚拟环境：%~dp0.venv
  echo 请先运行：.\setup.cmd
  exit /b 1
)

"%PY_EXE%" -m web %*
endlocal
```

- [ ] **Step 2: 在 README 中新增 Web 服务章节**

在 `README.md` 的 `## 使用说明` 之前插入：

````markdown
## Web 服务

除命令行外，项目还提供基于 FastAPI 的网页版。启动后浏览器打开 `http://127.0.0.1:8000`，粘贴抖音或小红书链接即可下载视频。

```powershell
# Windows 一键启动
.\run-web.cmd

# 或手动启动
.venv\Scripts\python.exe -m web
```

```bash
# macOS / Linux
python -m web

# 自定义监听地址
python -m web --host 0.0.0.0 --port 9000
```

接口示例：

```bash
curl -X POST http://127.0.0.1:8000/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://v.douyin.com/xxxx/"}'
```

成功时直接返回 `video/mp4` 文件流；失败返回 JSON `{"detail": "..."}`。当前网页版仅支持视频，小红书图集会返回 400。抖音解析需要启动无头浏览器，通常耗时 10–30 秒。

````

- [ ] **Step 3: 更新项目结构说明**

把 `README.md` 中 `## 项目结构` 的代码块替换为：

````text
spider-cli/
├── core/                  # 平台抓取逻辑，与界面无关
│   ├── douyin_spider.py   # 抖音爬虫（Playwright）
│   ├── xhs_spider.py      # 小红书爬虫（requests）
│   └── utils.py           # 链接提取、平台识别、文件名清理
├── cli/                   # 命令行前端
│   ├── main.py            # 入口、平台识别与分发
│   └── tui.py             # prompt_toolkit 菜单与行内输入
├── web/                   # FastAPI Web 前端
│   ├── app.py             # 路由、静态资源、并发限制
│   ├── service.py         # 下载编排与临时目录管理
│   └── static/            # 单页界面（HTML/CSS/JS）
├── tests/                 # 单元测试
│   ├── test_douyin.py
│   ├── test_xhs.py
│   ├── test_web_service.py
│   └── test_web_app.py
├── stealth.min.js         # 抖音反检测注入脚本
├── pytest.ini             # 测试路径配置
├── requirements.txt       # 运行依赖
├── requirements-dev.txt   # 打包依赖
├── setup.cmd              # Windows 一键安装
├── run.cmd                # Windows 一键运行命令行
├── run-web.cmd            # Windows 一键运行 Web 服务
├── docs/                  # 设计与实施文档
└── videos/                # 默认下载目录（已加入 .gitignore）
````

并把该代码块后的说明句改为：

```text
`core/` 不依赖任何界面代码。`cli/` 与 `web/` 都只通过 `core` 复用抓取逻辑。
```

- [ ] **Step 4: 更新测试说明**

把 `README.md` 的 `## 测试` 段落中的说明句替换为：

```text
现有测试覆盖链接提取、平台识别、小红书 SSR 解析、文件名清理、构造参数、类常量、下载路径返回值、Web 下载编排和 FastAPI 端点，不需要网络，也不会启动浏览器。
```

- [ ] **Step 5: Commit**

```bash
git add run-web.cmd README.md
git commit -m "docs: 补充 Web 服务启动方式与项目结构

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: 全量验证

**Files:**
- 无新增文件

- [ ] **Step 1: 运行全部测试**

Run:

```bash
./.venv/Scripts/python.exe -m pytest -v
```

Expected: 所有测试 PASS，0 failed。

- [ ] **Step 2: 启动服务**

Run（后台启动）：

```bash
./.venv/Scripts/python.exe -m web --port 8765
```

Expected: 输出包含 `Uvicorn running on http://127.0.0.1:8765`。

- [ ] **Step 3: 验证健康检查与首页**

Run:

```bash
curl -s http://127.0.0.1:8765/health
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/
```

Expected: 第一行输出 `{"status":"ok"}`，第二行输出 `200`。

- [ ] **Step 4: 验证错误分支**

Run:

```bash
curl -s -X POST http://127.0.0.1:8765/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/video"}'
```

Expected: 返回 `{"detail":"仅支持抖音和小红书链接"}`。

- [ ] **Step 5: 浏览器手动验证（可选，需真实链接）**

打开 `http://127.0.0.1:8765`，粘贴一条公开的抖音或小红书视频链接：

- 输入框下方出现对应平台徽章。
- 点击"解析并下载"后按钮进入 loading，状态文案轮换。
- 成功后浏览器弹出保存文件，页面显示文件名与体积。
- 粘贴小红书图集链接时，页面显示"小红书图集暂不支持，当前仅支持视频"。

- [ ] **Step 6: 停止服务并收尾**

停止后台 uvicorn 进程，确认 `git status` 干净（除原有 `draw/455.png` 删除和 `.codewhale/` 未跟踪文件外）。

---

## 自检结果

- 规格覆盖：core 返回值（Task 2/3）、下载编排（Task 4）、UI（Task 5）、API 与启动入口（Task 6）、依赖与文档（Task 1/7）、测试与验证（Task 8）均有对应任务。
- 占位符检查：所有代码步骤均给出完整实现，无 TBD/TODO。
- 类型一致性：`DownloadedFile(path, filename, temp_dir)`、`WebDownloadError(message, status_code)`、`create_spider(platform, url, save_dir, log_callback)`、`XhsSpider.resolve()`、`download_note(media)` 在各任务中命名一致。
