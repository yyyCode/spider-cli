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
