"""Platform spider factory shared by the CLI and web frontend."""

import os

SUPPORTED_PLATFORMS = ("douyin", "xhs")
UNSUPPORTED_PLATFORM_MESSAGE = "仅支持抖音和小红书链接"


def create_spider(platform, url, save_dir="videos", log_callback=None):
    """按平台创建爬虫；爬虫模块按需导入，避免未使用时加载 Playwright。"""
    if platform == "douyin":
        from .douyin_spider import DouyinSpider

        return DouyinSpider(url, save_dir=save_dir, log_callback=log_callback)
    if platform == "xhs":
        from .xhs_spider import XhsSpider

        return XhsSpider(
            url,
            save_dir=save_dir,
            cookie=os.environ.get("XHS_COOKIE"),
            log_callback=log_callback,
        )
    return None
