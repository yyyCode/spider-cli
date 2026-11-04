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
