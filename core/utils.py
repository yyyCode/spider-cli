"""Shared helpers for URL extraction, platform detection and filenames."""

import re
from urllib.parse import urlparse

# RFC 3986 常用字符，保留 ? & = % 等查询参数，遇到中文和表情自动停止
_URL_CHARS = r"A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%"
_URL_RE = re.compile(rf"https?://[{_URL_CHARS}]+")
_TRAILING_PUNCT = ".,;:!?)]}'\">"


def extract_url_from_text(text):
    """从混合文本中提取第一个完整链接，保留查询参数。"""
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(_TRAILING_PUNCT)


def sanitize_filename(name, max_len=50):
    """清理 Windows 非法字符，并限制长度。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name or "").strip()
    name = name.rstrip(" .")
    if not name:
        return ""
    return name[:max_len].rstrip(" .")


def detect_platform(url):
    """根据域名判断链接属于哪个平台。"""
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if (
        host in {"douyin.com", "iesdouyin.com"}
        or host.endswith(".douyin.com")
        or host.endswith(".iesdouyin.com")
    ):
        return "douyin"
    if (
        host in {"xiaohongshu.com", "xhslink.com"}
        or host.endswith(".xiaohongshu.com")
        or host.endswith(".xhslink.com")
    ):
        return "xhs"
    return None
