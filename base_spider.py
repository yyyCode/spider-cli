import re
import time
import os
import sys

# Set PLAYWRIGHT_BROWSERS_PATH before importing playwright (required for frozen/EXE builds)
if getattr(sys, 'frozen', False):
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        base_path = sys._MEIPASS
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(base_path, "ms-playwright")

import requests
from playwright.sync_api import sync_playwright


class BaseSpider:
    """Base spider with common browser lifecycle, stealth injection, video download logic.

    Subclasses override:
        - DEFAULT_REFERER: the Referer header value for the target platform
        - handle_response(): platform-specific network response interception
        - extract_title(): platform-specific page title extraction
    """

    DEFAULT_REFERER = ""

    MIN_VIDEO_SIZE = 1024 * 1024  # 1MB, filter ads/small files
    CHUNK_SIZE = 8192
    PAGE_TIMEOUT = 60000
    VIDEO_WAIT_TIMEOUT = 15000
    MOUSE_MOVE_WAIT = 2
    MAX_TITLE_LEN = 50
    VIEWPORT_WIDTH = 1920
    VIEWPORT_HEIGHT = 1080

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
            "Referer": self.DEFAULT_REFERER,
        }

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[Spider] {message}")

    def handle_response(self, response):
        """Platform-specific network response interception.

        Subclasses must override this to detect and capture video URLs from
        network responses (e.g. by checking content-type or URL patterns).
        """
        raise NotImplementedError

    def extract_title(self, page):
        """Platform-specific page title extraction.

        Subclasses must override this to extract the video title from the page.
        Return a raw string (sanitization and fallback are handled by run()).
        """
        raise NotImplementedError

    def run(self):
        with sync_playwright() as p:
            self.log(f"正在启动浏览器 (Headless={self.headless})...")
            try:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=['--start-maximized'] if not self.headless else [],
                )
            except Exception as e:
                self.log(f"启动浏览器失败: {e}")
                self.log("尝试使用 playwright install 安装浏览器...")
                return

            context = browser.new_context(
                viewport={'width': self.VIEWPORT_WIDTH, 'height': self.VIEWPORT_HEIGHT},
                user_agent=self.headers["User-Agent"],
            )

            # Inject stealth script (anti-detection)
            stealth_path = "stealth.min.js"
            if getattr(sys, 'frozen', False):
                stealth_path = os.path.join(sys._MEIPASS, "stealth.min.js")

            if os.path.exists(stealth_path):
                self.log(f"加载反爬脚本: {stealth_path}")
                context.add_init_script(path=stealth_path)
            else:
                self.log("警告: 未找到反爬脚本 stealth.min.js")

            page = context.new_page()

            # Listen for network responses (platform-specific interception)
            page.on("response", self.handle_response)

            self.log(f"正在访问: {self.url}")
            try:
                page.goto(self.url, timeout=self.PAGE_TIMEOUT)
            except Exception as e:
                self.log(f"页面加载超时或出错: {e}")

            # Wait for video element to appear
            try:
                page.wait_for_selector('video', timeout=self.VIDEO_WAIT_TIMEOUT)
                page.wait_for_load_state('networkidle', timeout=self.PAGE_TIMEOUT)

                # Simulate mouse movement to trigger lazy loading
                page.mouse.move(100, 100)
                page.mouse.move(200, 200)
                time.sleep(self.MOUSE_MOVE_WAIT)
            except Exception:
                self.log("等待视频元素超时")

            # Extract title (platform-specific)
            title = self.extract_title(page)
            title = re.sub(r'[\\/:*?"<>|]', '', title).strip()
            if not title:
                title = f"video_{int(time.time())}"
            if len(title) > self.MAX_TITLE_LEN:
                title = title[:self.MAX_TITLE_LEN]

            self.log(f"视频标题: {title}")

            # Select the largest video candidate (if any were captured by handle_response)
            target_url = None
            if self.video_candidates:
                self.video_candidates.sort(key=lambda x: x['size'], reverse=True)
                target_url = self.video_candidates[0]['url']
                self.log(
                    f"从 {len(self.video_candidates)} 个候选视频中选择了最大的: {target_url[:60]}..."
                )
            else:
                self.log("网络监听未捕获有效视频，尝试直接解析页面元素...")
                target_url = self._fallback_video_url(page)

            if target_url:
                filename = f"{title}.mp4"
                filepath = os.path.join(self.save_dir, filename)
                self.download_video(target_url, filepath)
            else:
                self.log("未能获取到视频链接。可能原因：")
                self.log("1. 视频是 blob 格式（加密流），当前爬虫暂不支持")
                self.log("2. 反爬虫检测拦截了请求")
                self.log("3. 需要登录")

            browser.close()

    def _fallback_video_url(self, page):
        """DOM fallback: try to extract video URL directly from page elements.

        Used when network interception did not capture any video candidates.
        Returns the URL string or None.
        """
        try:
            video_elem = page.query_selector('video')
            if video_elem:
                src = video_elem.get_attribute('src')
                if src and src.startswith('http'):
                    self.log(f"从页面元素获取 URL: {src}")
                    return src
                # Try <source> child tags
                sources = video_elem.query_selector_all('source')
                for s in sources:
                    s_src = s.get_attribute('src')
                    if s_src and s_src.startswith('http'):
                        self.log(f"从页面 source 标签获取 URL: {s_src}")
                        return s_src
        except Exception as e:
            self.log(f"页面解析出错: {e}")
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
