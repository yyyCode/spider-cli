"""Xiaohongshu note downloader for videos and image notes.

Uses the mobile SSR page, which embeds note data in
``window.__SETUP_SERVER_STATE__`` and works without a browser.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlparse

import requests

from utils import sanitize_filename

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
ORIGINAL_IMAGE_URL = "https://ci.xiaohongshu.com/{file_id}?imageView2/2/format/jpg"
NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item)/([0-9a-fA-F]+)")
LOGIN_PATH_MARKERS = ("/login", "/website-login", "/captcha")
CODEC_ORDER = ("h264", "h265", "av1", "h266")
CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


class XhsError(Exception):
    """Base error for Xiaohongshu parsing and download failures."""


class XhsLoginRequired(XhsError):
    """Raised when Xiaohongshu redirects to a login or captcha page."""


@dataclass
class NoteMedia:
    note_id: str
    title: str
    kind: str  # "video" or "images"
    video_urls: List[str] = field(default_factory=list)
    image_urls: List[List[str]] = field(default_factory=list)
    desc: str = ""


def _loads_tolerant(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = re.sub(r"(:\s*)undefined", r"\1null", raw)
        cleaned = re.sub(r"(\[\s*)undefined", r"\1null", cleaned)
        cleaned = re.sub(r"(,\s*)undefined", r"\1null", cleaned)
        cleaned = re.sub(r"(:\s*)NaN", r"\1null", cleaned)
        return json.loads(cleaned)


def _extract_json_after(html, marker):
    """读取 marker 赋值后的第一个 JSON 对象。"""
    match = re.search(re.escape(marker) + r"\s*=\s*", html)
    if match:
        start = html.find("{", match.end())
    else:
        marker_at = html.find(marker)
        if marker_at == -1:
            return None
        start = html.find("{", marker_at + len(marker))
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(html)):
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return _loads_tolerant(html[start:index + 1])
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


def extract_note_id(value):
    if not value:
        return ""
    match = NOTE_ID_RE.search(value)
    return match.group(1) if match else ""


def parse_setup_state(html):
    state = _extract_json_after(html, "__SETUP_SERVER_STATE__")
    if not isinstance(state, dict):
        return None
    page_data = state.get("LAUNCHER_SSR_STORE_PAGE_DATA") or {}
    note = page_data.get("noteData")
    return note if isinstance(note, dict) and note else None


def parse_initial_state(html, note_id=""):
    state = _extract_json_after(html, "__INITIAL_STATE__")
    if not isinstance(state, dict):
        return None
    details = (state.get("note") or {}).get("noteDetailMap") or {}
    if not isinstance(details, dict):
        return None

    if note_id and isinstance(details.get(note_id), dict):
        note = details[note_id].get("note")
        if isinstance(note, dict) and note:
            return note

    for entry in details.values():
        note = entry.get("note") if isinstance(entry, dict) else None
        if isinstance(note, dict) and (note.get("imageList") or note.get("video")):
            return note
    return None


def _dedupe(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _image_candidates(image):
    if not isinstance(image, dict):
        return []
    urls = []
    file_id = image.get("fileId") or image.get("file_id") or ""
    if file_id:
        urls.append(ORIGINAL_IMAGE_URL.format(file_id=file_id))
    urls.append(image.get("url"))
    for info in image.get("infoList") or []:
        if isinstance(info, dict):
            urls.append(info.get("url"))
    return _dedupe(urls)


def _video_candidates(note):
    stream = (((note.get("video") or {}).get("media") or {}).get("stream")) or {}
    urls = []
    for codec in CODEC_ORDER:
        entries = stream.get(codec) or []
        if not isinstance(entries, list):
            continue
        entries = [entry for entry in entries if isinstance(entry, dict)]
        entries.sort(
            key=lambda entry: (
                entry.get("size") or 0,
                (entry.get("width") or 0) * (entry.get("height") or 0),
            ),
            reverse=True,
        )
        for entry in entries:
            urls.append(entry.get("masterUrl"))
            for backup in entry.get("backupUrls") or []:
                urls.append(backup)
    return _dedupe(urls)


def _note_title(note, note_id):
    desc = (note.get("desc") or "").strip()
    title = (note.get("title") or "").strip()
    if not title and desc:
        title = desc.splitlines()[0].strip()
    if not title:
        title = note_id or f"xhs_{int(time.time())}"
    cleaned = sanitize_filename(title, 50)
    return cleaned or note_id or f"xhs_{int(time.time())}"


def parse_note(note, note_id=""):
    """把 noteData 转成统一的 NoteMedia；无法解析时返回 None。"""
    if not isinstance(note, dict) or not note:
        return None

    resolved_id = note.get("noteId") or note_id or ""
    images = [_image_candidates(image) for image in (note.get("imageList") or [])]
    images = [candidates for candidates in images if candidates]
    video_urls = _video_candidates(note)
    kind = "video" if (note.get("type") == "video" or video_urls) else "images"

    return NoteMedia(
        note_id=resolved_id,
        title=_note_title(note, resolved_id),
        kind=kind,
        video_urls=video_urls,
        image_urls=images,
        desc=note.get("desc") or "",
    )


class XhsSpider:
    REQUEST_TIMEOUT = 30
    DOWNLOAD_TIMEOUT = (10, 120)

    def __init__(self, url, save_dir="videos", cookie=None, log_callback=None, session=None):
        self.url = url
        self.save_dir = save_dir or "videos"
        self.cookie = cookie
        self.log_callback = log_callback
        self.session = session or requests.Session()
        self.headers = {
            "User-Agent": MOBILE_UA,
            "Referer": "https://www.xiaohongshu.com/",
        }
        if cookie:
            self.headers["Cookie"] = cookie

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[XHS] {message}")

    def fetch_html(self):
        response = self.session.get(
            self.url,
            headers=self.headers,
            timeout=self.REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        final_url = response.url
        if any(marker in final_url for marker in LOGIN_PATH_MARKERS):
            raise XhsLoginRequired(
                "访问被重定向到登录或验证码页面，请设置环境变量 XHS_COOKIE 后重试"
            )
        response.raise_for_status()
        return final_url, response.text

    def parse(self, final_url, html):
        note_id = extract_note_id(final_url) or extract_note_id(self.url)
        note = parse_setup_state(html) or parse_initial_state(html, note_id)
        if not note:
            raise XhsError("未解析到笔记数据，页面结构可能变化或内容需要登录")
        media = parse_note(note, note_id)
        if not media:
            raise XhsError("笔记数据为空")
        return media

    def run(self):
        try:
            final_url, html = self.fetch_html()
            media = self.parse(final_url, html)
            self.log(f"笔记: {media.title}（{'视频' if media.kind == 'video' else '图集'}）")
            return self.download_note(media)
        except XhsError as exc:
            self.log(f"失败: {exc}")
            return False
        except requests.RequestException as exc:
            self.log(f"网络请求失败: {exc}")
            return False
        except OSError as exc:
            self.log(f"文件写入失败: {exc}")
            return False

    def download_note(self, media):
        out_dir = os.path.join(self.save_dir, media.title)
        os.makedirs(out_dir, exist_ok=True)
        if media.kind == "video":
            return self._download_video(media, out_dir)
        return self._download_images(media, out_dir)

    def _download_video(self, media, out_dir):
        if not media.video_urls:
            self.log("未找到视频地址，可能是动图或受限内容")
            return False

        filepath = os.path.join(out_dir, f"{media.title}.mp4")
        if self._is_complete(filepath):
            self.log(f"已存在，跳过: {filepath}")
            return True

        for url in media.video_urls:
            if self._download_file(url, filepath, expect="video"):
                self.log(f"下载完成: {filepath}")
                return True
        self.log("视频下载失败: 所有候选地址均不可用")
        return False

    def _download_images(self, media, out_dir):
        if not media.image_urls:
            self.log("未找到图片地址")
            return False

        success = 0
        failed = 0
        for index, candidates in enumerate(media.image_urls, start=1):
            existing = self._find_existing(out_dir, index)
            if existing:
                self.log(f"已存在，跳过: 第 {index} 张")
                success += 1
                continue

            placeholder = os.path.join(out_dir, f"{index:02d}.jpg")
            downloaded = False
            for url in candidates:
                path = self._download_file(
                    url, placeholder, expect="image", return_path=True
                )
                if path:
                    self.log(f"下载完成: {path}")
                    success += 1
                    downloaded = True
                    break
            if not downloaded:
                failed += 1
                self.log(f"第 {index} 张图片下载失败")

        self.log(f"图片处理完成: 成功 {success}, 失败 {failed}")
        return success > 0

    @staticmethod
    def _is_complete(path):
        return os.path.isfile(path) and os.path.getsize(path) > 0

    @staticmethod
    def _find_existing(out_dir, index):
        prefix = f"{index:02d}."
        for name in os.listdir(out_dir):
            if name.startswith(prefix):
                path = os.path.join(out_dir, name)
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    return path
        return None

    @staticmethod
    def _extension_from_url(url):
        path = urlparse(url).path.lower()
        extension = os.path.splitext(path)[1]
        return extension if extension in IMAGE_EXTENSIONS else ""

    def _download_file(self, url, path, expect, return_path=False):
        failure = None if return_path else False
        temp_path = path + ".part"
        try:
            with self.session.get(
                url,
                headers=self.headers,
                stream=True,
                timeout=self.DOWNLOAD_TIMEOUT,
            ) as response:
                if response.status_code != 200:
                    self.log(f"下载失败 {response.status_code}: {url[:80]}")
                    return failure

                content_type = (
                    response.headers.get("content-type") or ""
                ).split(";")[0].strip().lower()
                allowed = (
                    content_type.startswith("image/")
                    if expect == "image"
                    else content_type.startswith("video/")
                )
                if content_type and content_type != "application/octet-stream" and not allowed:
                    self.log(f"跳过非{expect}响应 ({content_type}): {url[:80]}")
                    return failure

                with open(temp_path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            handle.write(chunk)

            if os.path.getsize(temp_path) == 0:
                os.remove(temp_path)
                return failure

            final_path = path
            if expect == "image":
                extension = CONTENT_TYPE_EXT.get(content_type)
                if not extension:
                    extension = self._extension_from_url(url) or ".jpg"
                final_path = os.path.splitext(path)[0] + extension

            os.replace(temp_path, final_path)
            return final_path if return_path else True
        except (requests.RequestException, OSError) as exc:
            self.log(f"下载出错: {exc}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return failure


if __name__ == "__main__":
    print("=" * 50)
    print("小红书笔记学习爬虫")
    print("注意：本脚本仅供学习交流，请勿用于非法用途")
    print("=" * 50)
    raw = input("请粘贴小红书笔记链接: ").strip()
    if raw:
        XhsSpider(raw).run()
    else:
        print("未输入内容，程序退出")
