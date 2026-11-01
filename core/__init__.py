"""Platform download logic shared by every frontend (CLI, future UI/web).

Import from the submodules directly, e.g. ``from core.xhs_spider import XhsSpider``,
so callers that only need one platform don't pay for the other's imports
(``core.douyin_spider`` pulls in Playwright at import time).
"""
