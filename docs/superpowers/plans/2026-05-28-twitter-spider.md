# Twitter/X Video Spider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Twitter/X video link support with an extensible BaseSpider architecture that both DouyinSpider and TwitterSpider inherit from.

**Architecture:** Extract common browser lifecycle, stealth injection, and download logic into `BaseSpider`. `DouyinSpider` and `TwitterSpider` override `handle_response()`, `extract_title()`, and `DEFAULT_REFERER`. CLI detects platform from URL domain and routes to the correct spider.

**Tech Stack:** Python 3, Playwright (sync), requests, prompt_toolkit

---

### Task 1: Create base_spider.py

**Files:**
- Create: `base_spider.py`

Extract all common logic from `DouyinSpider` into a `BaseSpider` class. The base class handles browser lifecycle, stealth injection, page navigation, title sanitization, video candidate selection, and download. Subclasses override `handle_response()`, `extract_title()`, and `DEFAULT_REFERER`.

- [ ] **Step 1: Write base_spider.py**

```python
import re
import time
import os
import sys

if getattr(sys, 'frozen', False):
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        base_path = sys._MEIPASS
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(base_path, "ms-playwright")

import requests
from playwright.sync_api import sync_playwright


class BaseSpider:
    MIN_VIDEO_SIZE = 1024 * 1024
    CHUNK_SIZE = 8192
    PAGE_TIMEOUT = 60000
    VIDEO_WAIT_TIMEOUT = 15000
    MOUSE_MOVE_WAIT = 2
    MAX_TITLE_LEN = 50
    VIEWPORT_WIDTH = 1920
    VIEWPORT_HEIGHT = 1080

    DEFAULT_REFERER = ""

    def __init__(self, url, headless=True, log_callback=None, save_dir="videos"):
        self.url = url
        self.headless = headless
        self.log_callback = log_callback
        self.video_candidates = []
        self.save_dir = save_dir or "videos"

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
            self.log(f"已创建下载目录: {self.save_dir}")

    @property
    def headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.DEFAULT_REFERER
        }

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[Spider] {message}")

    def handle_response(self, response):
        raise NotImplementedError("Subclass must implement handle_response")

    def extract_title(self, page):
        raise NotImplementedError("Subclass must implement extract_title")

    def run(self):
        with sync_playwright() as p:
            self.log(f"正在启动浏览器 (Headless={self.headless})...")
            try:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=['--start-maximized'] if not self.headless else []
                )
            except Exception as e:
                self.log(f"启动浏览器失败: {e}")
                self.log("尝试使用 playwright install 安装浏览器...")
                return

            context = browser.new_context(
                viewport={'width': self.VIEWPORT_WIDTH, 'height': self.VIEWPORT_HEIGHT},
                user_agent=self.headers["User-Agent"]
            )

            stealth_path = "stealth.min.js"
            if getattr(sys, 'frozen', False):
                stealth_path = os.path.join(sys._MEIPASS, "stealth.min.js")

            if os.path.exists(stealth_path):
                self.log(f"加载反爬脚本: {stealth_path}")
                context.add_init_script(path=stealth_path)
            else:
                self.log("警告: 未找到反爬脚本 stealth.min.js")

            page = context.new_page()
            page.on("response", self.handle_response)

            self.log(f"正在访问: {self.url}")
            try:
                page.goto(self.url, timeout=self.PAGE_TIMEOUT)
            except Exception as e:
                self.log(f"页面加载超时或出错: {e}")

            try:
                page.wait_for_selector('video', timeout=self.VIDEO_WAIT_TIMEOUT)
                page.wait_for_load_state('networkidle', timeout=self.PAGE_TIMEOUT)
                page.mouse.move(100, 100)
                page.mouse.move(200, 200)
                time.sleep(self.MOUSE_MOVE_WAIT)
            except Exception:
                self.log("等待视频元素超时")

            raw_title = self.extract_title(page)
            title = re.sub(r'[\\/:*?"<>|]', '', raw_title).strip()
            if not title:
                title = f"video_{int(time.time())}"
            if len(title) > self.MAX_TITLE_LEN:
                title = title[:self.MAX_TITLE_LEN]

            self.log(f"视频标题: {title}")

            target_url = None
            if self.video_candidates:
                self.video_candidates.sort(key=lambda x: x['size'], reverse=True)
                target_url = self.video_candidates[0]['url']
                self.log(f"从 {len(self.video_candidates)} 个候选视频中选择了最大的")
            else:
                self.log("网络监听未捕获有效视频，尝试直接解析页面元素...")
                target_url = self._fallback_video_url(page)

            if target_url:
                filename = f"{title}.mp4"
                filepath = os.path.join(self.save_dir, filename)
                self.download_video(target_url, filepath)
            else:
                self.log("未能获取到视频链接。")

            browser.close()

    def _fallback_video_url(self, page):
        try:
            video_elem = page.query_selector('video')
            if video_elem:
                src = video_elem.get_attribute('src')
                if src and src.startswith('http'):
                    return src
                sources = video_elem.query_selector_all('source')
                for s in sources:
                    s_src = s.get_attribute('src')
                    if s_src and s_src.startswith('http'):
                        return s_src
        except Exception:
            pass
        return None

    def download_video(self, url, filepath):
        self.log(f"开始下载: {filepath}")
        try:
            response = requests.get(url, headers=self.headers, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                self.log(f"下载完成！文件已保存至: {filepath}")
            else:
                self.log(f"下载失败，状态码: {response.status_code}")
        except Exception as e:
            self.log(f"下载出错: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add base_spider.py
git commit -m "feat: extract BaseSpider from DouyinSpider with common browser/download logic

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Refactor douyin_spider.py to inherit BaseSpider

**Files:**
- Modify: `douyin_spider.py` (full rewrite, shrink from ~227 to ~60 lines)

Remove all logic now provided by `BaseSpider`, leaving only Douyin-specific `handle_response()`, `extract_title()`, `DEFAULT_REFERER`, and the utility `extract_url_from_text()`.

- [ ] **Step 1: Rewrite douyin_spider.py**

```python
from base_spider import BaseSpider


class DouyinSpider(BaseSpider):
    DEFAULT_REFERER = "https://www.douyin.com/"

    def handle_response(self, response):
        try:
            if response.status == 200 and ('video/mp4' in response.headers.get('content-type', '') or '.mp4' in response.url):
                content_length = int(response.headers.get('content-length', 0))
                if content_length > self.MIN_VIDEO_SIZE:
                    self.log(f"捕获视频流: 大小={content_length/1024/1024:.2f}MB, URL={response.url[:60]}...")
                    self.video_candidates.append({
                        'url': response.url,
                        'size': content_length
                    })
                else:
                    self.log(f"忽略小文件(可能是广告): 大小={content_length/1024}KB, URL={response.url[:60]}...")
        except Exception:
            pass

    def extract_title(self, page):
        title = page.title()
        if not title or title == "抖音":
            try:
                title = page.locator('.desc').first.inner_text()
            except Exception:
                pass
        return (title or "").strip()


def extract_url_from_text(text):
    import re
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    if urls:
        return urls[0]
    return None
```

- [ ] **Step 2: Run existing tests to verify nothing broke**

```bash
python -m pytest test_spider.py -v
```

Expected: All 9 existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add douyin_spider.py
git commit -m "refactor: make DouyinSpider inherit BaseSpider

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Create twitter_spider.py

**Files:**
- Create: `twitter_spider.py`

Implement `TwitterSpider(BaseSpider)` that intercepts Twitter's GraphQL API responses, parses JSON recursively for video variants, and extracts the highest-bitrate MP4 URL. Title comes from `og:title` meta tag.

- [ ] **Step 1: Write twitter_spider.py**

```python
from base_spider import BaseSpider


class TwitterSpider(BaseSpider):
    DEFAULT_REFERER = "https://x.com/"

    def handle_response(self, response):
        try:
            if '/i/api/graphql/' not in response.url:
                return
            if response.status != 200:
                return
            body = response.json()
            variants = self._find_variants(body)
            if variants:
                for v in variants:
                    if v.get('content_type') == 'video/mp4':
                        bitrate = v.get('bitrate', 0)
                        url = v.get('url', '')
                        if url and bitrate > 0:
                            self.video_candidates.append({
                                'url': url,
                                'size': bitrate
                            })
        except Exception:
            pass

    def _find_variants(self, obj):
        if isinstance(obj, dict):
            if 'variants' in obj and isinstance(obj['variants'], list):
                for v in obj['variants']:
                    if isinstance(v, dict) and v.get('content_type') == 'video/mp4':
                        return obj['variants']
            for v in obj.values():
                result = self._find_variants(v)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_variants(item)
                if result:
                    return result
        return None

    def extract_title(self, page):
        try:
            og_title = page.locator('meta[property="og:title"]').get_attribute('content')
            if og_title:
                return og_title.strip()
        except Exception:
            pass
        return page.title() or ""
```

- [ ] **Step 2: Commit**

```bash
git add twitter_spider.py
git commit -m "feat: add TwitterSpider with GraphQL API interception

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Update cli.py with platform detection and routing

**Files:**
- Modify: `cli.py` (lines 1, 148-221)

Add `detect_platform()`, import `TwitterSpider`, update branding text, and route URLs to the correct spider.

- [ ] **Step 1: Update imports and add detect_platform**

Replace the import section (line 1) and add `detect_platform` after it:

```python
from douyin_spider import DouyinSpider, extract_url_from_text
from twitter_spider import TwitterSpider
import sys
import os
import re
import traceback


def detect_platform(url):
    if re.search(r'douyin\.com', url):
        return 'douyin'
    if re.search(r'x\.com|twitter\.com', url):
        return 'twitter'
    return 'unknown'
```

- [ ] **Step 2: Update branding text**

Change line 149-150 from:
```python
print("抖音视频爬虫命令行版 v1.0")
print("功能：自动过滤广告，下载高清无水印(尽可能)视频")
```
To:
```python
print("社交媒体视频爬虫 v2.0")
print("支持抖音、推特/X | 自动过滤广告，下载高清无水印视频")
```

- [ ] **Step 3: Update the "start" action to route by platform**

Change lines 201-221 (the `if action == "start":` block). Replace:
```python
            if action == "start":
                raw_input = _try_tui(
                    use_tui_ref,
                    lambda: _input_tui("请粘贴分享口令或链接："),
                    lambda: _plain_input("请输入分享口令或链接:", prefix="\n"),
                    "交互式输入不可用，已回退到普通输入",
                )

                if not raw_input:
                    continue

                url = extract_url_from_text(raw_input)
                if not url:
                    print("错误: 未识别到有效链接，请重新输入。")
                    continue

                print(f"正在启动爬虫抓取: {url}")
                spider = DouyinSpider(url, save_dir=save_dir)
                spider.run()
                print("----------------------------------------")
                continue
```

With:
```python
            if action == "start":
                raw_input = _try_tui(
                    use_tui_ref,
                    lambda: _input_tui("请粘贴分享口令或链接："),
                    lambda: _plain_input("请输入分享口令或链接:", prefix="\n"),
                    "交互式输入不可用，已回退到普通输入",
                )

                if not raw_input:
                    continue

                url = extract_url_from_text(raw_input)
                if not url:
                    print("错误: 未识别到有效链接，请重新输入。")
                    continue

                platform = detect_platform(url)
                if platform == 'douyin':
                    spider = DouyinSpider(url, save_dir=save_dir)
                elif platform == 'twitter':
                    spider = TwitterSpider(url, save_dir=save_dir)
                else:
                    print("错误: 未识别的平台链接（目前支持抖音和推特/X）。")
                    continue

                print(f"正在启动爬虫抓取: {url}")
                spider.run()
                print("----------------------------------------")
                continue
```

- [ ] **Step 4: Commit**

```bash
git add cli.py
git commit -m "feat: add platform detection and Twitter routing to CLI

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Add tests for new code

**Files:**
- Modify: `test_spider.py`

Add tests for `detect_platform`, `BaseSpider`, and `TwitterSpider`.

- [ ] **Step 1: Add new tests to test_spider.py**

Append to `test_spider.py`:

```python
from base_spider import BaseSpider
from twitter_spider import TwitterSpider
from cli import detect_platform


class TestDetectPlatform:
    def test_detect_douyin(self):
        assert detect_platform("https://v.douyin.com/abc123/") == "douyin"
        assert detect_platform("https://www.douyin.com/video/123") == "douyin"

    def test_detect_twitter_x(self):
        assert detect_platform("https://x.com/user/status/123") == "twitter"

    def test_detect_twitter_com(self):
        assert detect_platform("https://twitter.com/user/status/123") == "twitter"

    def test_detect_unknown_url(self):
        assert detect_platform("https://youtube.com/watch?v=123") == "unknown"

    def test_detect_unknown_text(self):
        assert detect_platform("not a url") == "unknown"

    def test_detect_empty_string(self):
        assert detect_platform("") == "unknown"


class TestBaseSpider:
    def test_init_defaults(self):
        spider = BaseSpider("https://example.com")
        assert spider.url == "https://example.com"
        assert spider.headless is True
        assert spider.video_candidates == []

    def test_init_custom_save_dir(self):
        spider = BaseSpider("https://example.com", save_dir="test_dir")
        assert spider.save_dir == "test_dir"

    def test_init_headless_false(self):
        spider = BaseSpider("https://example.com", headless=False)
        assert spider.headless is False

    def test_headers_contain_user_agent(self):
        spider = BaseSpider("https://example.com")
        assert "User-Agent" in spider.headers
        assert "Referer" in spider.headers

    def test_handle_response_raises(self):
        spider = BaseSpider("https://example.com")
        with pytest.raises(NotImplementedError):
            spider.handle_response(None)

    def test_extract_title_raises(self):
        spider = BaseSpider("https://example.com")
        with pytest.raises(NotImplementedError):
            spider.extract_title(None)


class TestTwitterSpider:
    def test_init(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        assert spider.url == "https://x.com/user/status/123"
        assert spider.DEFAULT_REFERER == "https://x.com/"

    def test_headers_referer(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        assert spider.headers["Referer"] == "https://x.com/"

    def test_find_variants_empty(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        assert spider._find_variants({}) is None

    def test_find_variants_found(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        data = {
            "data": {
                "tweetResult": {
                    "result": {
                        "legacy": {
                            "extended_entities": {
                                "media": [{
                                    "video_info": {
                                        "variants": [
                                            {"content_type": "video/mp4", "bitrate": 1000, "url": "https://video.twimg.com/test.mp4"},
                                            {"content_type": "application/x-mpegURL", "bitrate": 0, "url": "https://video.twimg.com/test.m3u8"}
                                        ]
                                    }
                                }]
                            }
                        }
                    }
                }
            }
        }
        result = spider._find_variants(data)
        assert result is not None
        assert len(result) == 2
        assert result[0]["content_type"] == "video/mp4"
```

- [ ] **Step 2: Run all tests**

```bash
python -m pytest test_spider.py -v
```

Expected: All tests pass (9 existing + 15 new = 24 tests).

- [ ] **Step 3: Commit**

```bash
git add test_spider.py
git commit -m "test: add tests for BaseSpider, TwitterSpider, and detect_platform

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest test_spider.py -v
```

Expected: 24 tests pass.

- [ ] **Step 2: Verify imports work standalone**

```bash
python -c "from base_spider import BaseSpider; from douyin_spider import DouyinSpider, extract_url_from_text; from twitter_spider import TwitterSpider; from cli import detect_platform; print('All imports OK')"
```

Expected: `All imports OK`

- [ ] **Step 3: Check git log**

```bash
git log --oneline -6
```

Expected: Clean commit history with 6 commits on `dev-twitter`.
