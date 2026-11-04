import time
import os
import sys

# 同样在爬虫模块中设置环境变量，确保独立运行时或被调用时都能找到浏览器
# 必须在导入 playwright 之前设置
# 仅在打包环境下强制设置，开发环境下如果不设置则使用默认（通常是用户目录）
if getattr(sys, 'frozen', False):
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        base_path = sys._MEIPASS
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(base_path, "ms-playwright")

import requests
from playwright.sync_api import sync_playwright

from .utils import extract_url_from_text, sanitize_filename

class DouyinSpider:
    MIN_VIDEO_SIZE = 1024 * 1024  # 1MB，过滤广告/小文件
    CHUNK_SIZE = 64 * 1024
    PAGE_TIMEOUT = 60000
    CANDIDATE_WAIT_TIMEOUT = 30000  # 毫秒；捕获到候选后立即继续
    CANDIDATE_POLL_INTERVAL = 250  # 毫秒
    DOWNLOAD_TIMEOUT = (10, 120)  # (连接超时, 读取超时)
    MAX_TITLE_LEN = 50
    VIEWPORT_WIDTH = 1920
    VIEWPORT_HEIGHT = 1080

    def __init__(self, url, headless=True, log_callback=None, save_dir="videos"):
        self.url = url
        self.headless = headless
        self.log_callback = log_callback
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/"
        }
        self.video_candidates = [] # 存储所有候选视频
        self.save_dir = save_dir or "videos"

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
            self.log(f"已创建下载目录: {self.save_dir}")

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[Spider] {message}")

    def handle_response(self, response):
        """
        监听网络响应，获取视频流地址
        """
        try:
            # 抖音视频流通常是 .mp4 结尾或者 content-type 为 video/mp4
            # 或者是 blob 链接（但 blob 无法直接 requests 下载，这里主要关注 mp4）
            if response.status == 200 and ('video/mp4' in response.headers.get('content-type', '') or '.mp4' in response.url):
                content_length = int(response.headers.get('content-length', 0))
                url = response.url
                
                # 过滤掉太小的文件（小于 1MB 的通常是广告或图标特效）
                if content_length > self.MIN_VIDEO_SIZE:
                    self.log(f"捕获视频流: 大小={content_length/1024/1024:.2f}MB, URL={url[:60]}...")
                    self.video_candidates.append({
                        'url': url,
                        'size': content_length
                    })
                else:
                    self.log(f"忽略小文件(可能是广告): 大小={content_length/1024}KB, URL={url[:60]}...")
        except Exception:
            pass

    def _launch_browser(self, p):
        """优先使用完整 Chromium 的新无头模式。

        Playwright 默认会启动独立的 chrome-headless-shell.exe，Windows 首次
        运行时可能弹出安全/防火墙确认，非交互部署会卡住。完整 Chromium 可以
        避开这个额外二进制，也更接近真实浏览器；channel 不可用时回退默认启动。
        """
        if self.headless:
            try:
                return p.chromium.launch(headless=True, channel="chromium")
            except Exception as e:
                self.log(f"完整 Chromium 启动失败，回退默认 headless: {e}")
        args = [] if self.headless else ['--start-maximized']
        return p.chromium.launch(headless=self.headless, args=args)

    def _navigate(self, page):
        """只等 DOM 就绪，不等待 load/networkidle。

        抖音页面会持续加载媒体和统计请求，等 ``load`` 实测可能要几十秒，
        而视频流地址在 DOM 就绪、脚本开始播放后就能通过网络监听拿到。
        """
        return page.goto(
            self.url,
            timeout=self.PAGE_TIMEOUT,
            wait_until="domcontentloaded",
        )

    def _wait_for_candidates(self, page):
        """轮询网络监听结果，命中候选后立即返回，避免固定等待。"""
        deadline = time.time() + self.CANDIDATE_WAIT_TIMEOUT / 1000
        while time.time() < deadline and not self.video_candidates:
            page.wait_for_timeout(self.CANDIDATE_POLL_INTERVAL)
        return bool(self.video_candidates)

    def _cookie_header(self, context):
        """把浏览器 Cookie 转成 requests 可用的请求头。"""
        return "; ".join(
            f"{cookie['name']}={cookie['value']}" for cookie in context.cookies()
        )

    def run(self):
        with sync_playwright() as p:
            self.log(f"正在启动浏览器 (Headless={self.headless})...")
            try:
                browser = self._launch_browser(p)
            except Exception as e:
                self.log(f"启动浏览器失败: {e}")
                self.log("尝试使用 playwright install 安装浏览器...")
                return

            # 创建上下文
            context = browser.new_context(
                viewport={'width': self.VIEWPORT_WIDTH, 'height': self.VIEWPORT_HEIGHT},
                user_agent=self.headers["User-Agent"]
            )
            
            # 注入防检测脚本
            # 适配 EXE 打包路径和开发环境路径
            stealth_path = "stealth.min.js"
            if getattr(sys, 'frozen', False):
                stealth_path = os.path.join(sys._MEIPASS, "stealth.min.js")
            else:
                # core/ 在仓库根目录下一层，优先使用项目根目录的脚本
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                candidate = os.path.join(project_root, "stealth.min.js")
                if os.path.exists(candidate):
                    stealth_path = candidate
            
            if os.path.exists(stealth_path):
                self.log(f"加载反爬脚本: {stealth_path}")
                context.add_init_script(path=stealth_path)
            else:
                self.log("警告: 未找到反爬脚本 stealth.min.js")

            page = context.new_page()
            
            # 监听网络请求
            page.on("response", self.handle_response)

            self.log(f"正在访问: {self.url}")
            nav_start = time.time()
            try:
                self._navigate(page)
                self.log(f"页面已就绪，耗时 {time.time() - nav_start:.1f}s")
            except Exception as e:
                self.log(f"页面加载超时或出错: {e}")

            wait_start = time.time()
            self.log("等待视频流...")
            try:
                # 模拟鼠标移动，触发视频加载
                page.mouse.move(100, 100)
                page.mouse.move(200, 200)
                captured = self._wait_for_candidates(page)
            except Exception as e:
                self.log(f"等待视频流出错: {e}")
                captured = bool(self.video_candidates)

            if captured:
                self.log(
                    f"捕获候选视频 {len(self.video_candidates)} 个，"
                    f"耗时 {time.time() - wait_start:.1f}s"
                )
            else:
                self.log(
                    f"未捕获候选视频，尝试页面元素回退"
                    f"（等待 {time.time() - wait_start:.1f}s）"
                )

            # 获取标题
            title = sanitize_filename(page.title(), self.MAX_TITLE_LEN)
            if not title or title == "抖音":
                try:
                    desc = page.locator('.desc').first.inner_text()
                    title = sanitize_filename(desc, self.MAX_TITLE_LEN)
                except Exception:
                    pass

            if not title:
                title = f"douyin_{int(time.time())}"
            
            self.log(f"视频标题: {title}")

            # 策略优化：选择最大的视频文件
            target_url = None
            if self.video_candidates:
                # 按大小排序，取最大的
                self.video_candidates.sort(key=lambda x: x['size'], reverse=True)
                target_url = self.video_candidates[0]['url']
                self.log(f"从 {len(self.video_candidates)} 个候选视频中选择了最大的: {target_url[:60]}...")
            else:
                self.log("网络监听未捕获有效视频，尝试直接解析页面元素...")
                try:
                    video_elem = page.query_selector('video')
                    if video_elem:
                        src = video_elem.get_attribute('src')
                        # 有时候 src 是 blob:，这种无法直接下载。如果是 http 开头则可以使用
                        if src and src.startswith('http'):
                            target_url = src
                            self.log(f"从页面元素获取 URL: {target_url}")
                        else:
                            # 尝试获取 source 子标签
                            sources = video_elem.query_selector_all('source')
                            for s in sources:
                                s_src = s.get_attribute('src')
                                if s_src and s_src.startswith('http'):
                                    target_url = s_src
                                    break
                except Exception as e:
                    self.log(f"页面解析出错: {e}")

            # 先关闭浏览器再下载：否则浏览器可能还在拉取同一视频流，
            # 与 requests 争抢带宽，导致下载时间翻倍。
            cookie_header = self._cookie_header(context)
            if cookie_header:
                self.headers["Cookie"] = cookie_header
            browser.close()

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

            return result

    def download_video(self, url, filepath):
        self.log(f"开始下载: {filepath}")
        started = time.time()
        try:
            # 抖音视频链接通常需要带上 headers（含 Cookie）避免 403
            with requests.get(
                url,
                headers=self.headers,
                stream=True,
                timeout=self.DOWNLOAD_TIMEOUT,
            ) as response:
                if response.status_code == 200:
                    size = 0
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                size += len(chunk)
                    elapsed = max(time.time() - started, 0.001)
                    speed = size / 1024 / 1024 / elapsed
                    self.log(
                        f"下载完成！{size / 1024 / 1024:.2f}MB，"
                        f"耗时 {elapsed:.1f}s，平均 {speed:.2f}MB/s"
                    )
                    return filepath
                self.log(f"下载失败，状态码: {response.status_code}")
        except Exception as e:
            self.log(f"下载出错: {e}")
        return None

if __name__ == "__main__":
    print("="*50)
    print("抖音视频学习爬虫 (Playwright版)")
    print("注意：本脚本仅供学习交流，请勿用于非法用途")
    print("="*50)
    
    # 提示用户输入
    raw_input = input("请粘贴抖音分享文本 (包含链接即可): ")
    
    if raw_input:
        target_url = extract_url_from_text(raw_input)
        
        if target_url:
            print(f"识别到链接: {target_url}")
            spider = DouyinSpider(target_url)
            spider.run()
        else:
            print("未在输入中识别到有效的 http/https 链接")
    else:
        print("未输入内容，程序退出")
