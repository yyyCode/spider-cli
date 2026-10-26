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
