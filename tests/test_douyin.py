"""Tests for the Douyin spider and shared URL helpers."""
from core.douyin_spider import DouyinSpider
from core.utils import extract_url_from_text


class TestExtractUrlFromText:
    def test_extract_http_url(self):
        result = extract_url_from_text("https://v.douyin.com/abc123/")
        assert result == "https://v.douyin.com/abc123/"

    def test_extract_url_from_mixed_text(self):
        text = "这是抖音分享链接 https://v.douyin.com/xyz789/ 快来看看"
        result = extract_url_from_text(text)
        assert result == "https://v.douyin.com/xyz789/"

    def test_extract_first_url_when_multiple(self):
        result = extract_url_from_text(
            "https://v.douyin.com/first/ and https://v.douyin.com/second/"
        )
        assert result == "https://v.douyin.com/first/"

    def test_no_url_returns_none(self):
        result = extract_url_from_text("这只是一段普通文本没有链接")
        assert result is None

    def test_empty_string(self):
        result = extract_url_from_text("")
        assert result is None

    def test_extract_with_emoji(self):
        text = "😎🔥 https://v.douyin.com/test/ 🔥😎"
        result = extract_url_from_text(text)
        assert result == "https://v.douyin.com/test/"

    def test_extract_url_keeps_query_parameters(self):
        url = (
            "https://www.xiaohongshu.com/discovery/item/6adc"
            "?xsec_token=ABC=&xsec_source=pc_share"
        )
        assert extract_url_from_text(f"分享 {url} 快看") == url


class TestDouyinSpider:
    def test_init_defaults(self):
        spider = DouyinSpider("https://example.com")
        assert spider.url == "https://example.com"
        assert spider.headless is True
        assert spider.save_dir == "videos"

    def test_init_custom_save_dir(self):
        spider = DouyinSpider("https://example.com", save_dir="custom_videos")
        assert spider.save_dir == "custom_videos"

    def test_init_headless_false(self):
        spider = DouyinSpider("https://example.com", headless=False)
        assert spider.headless is False

    def test_video_candidates_empty_initially(self):
        spider = DouyinSpider("https://example.com")
        assert spider.video_candidates == []

    def test_class_constants(self):
        assert DouyinSpider.MIN_VIDEO_SIZE == 1024 * 1024
        assert DouyinSpider.CHUNK_SIZE == 8192
        assert DouyinSpider.MAX_TITLE_LEN == 50


class _FakeDownloadResponse:
    status_code = 200

    def iter_content(self, chunk_size=8192):
        yield b"fake-video-bytes"


class _ForbiddenResponse:
    status_code = 403

    def iter_content(self, chunk_size=8192):
        yield b""


class TestDouyinDownload:
    def test_download_video_returns_path(self, monkeypatch, tmp_path):
        spider = DouyinSpider("https://example.com", save_dir=str(tmp_path))
        monkeypatch.setattr(
            "core.douyin_spider.requests.get",
            lambda *args, **kwargs: _FakeDownloadResponse(),
        )
        target = tmp_path / "video.mp4"

        result = spider.download_video("https://cdn.example.com/x.mp4", str(target))

        assert result == str(target)
        assert target.read_bytes() == b"fake-video-bytes"

    def test_download_video_returns_none_on_http_error(self, monkeypatch, tmp_path):
        spider = DouyinSpider("https://example.com", save_dir=str(tmp_path))
        monkeypatch.setattr(
            "core.douyin_spider.requests.get",
            lambda *args, **kwargs: _ForbiddenResponse(),
        )
        target = tmp_path / "x.mp4"

        result = spider.download_video("https://cdn.example.com/x.mp4", str(target))

        assert result is None
        assert not target.exists()


class _FakeChromium:
    def __init__(self, fail_channel=False):
        self.calls = []
        self.fail_channel = fail_channel

    def launch(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_channel and kwargs.get("channel") == "chromium":
            raise RuntimeError("channel not installed")
        return "browser"


class _FakePlaywright:
    def __init__(self, fail_channel=False):
        self.chromium = _FakeChromium(fail_channel)


class TestDouyinBrowserLaunch:
    def test_headless_prefers_full_chromium(self, tmp_path):
        spider = DouyinSpider("https://example.com", save_dir=str(tmp_path))
        playwright = _FakePlaywright()

        assert spider._launch_browser(playwright) == "browser"
        assert playwright.chromium.calls == [
            {"headless": True, "channel": "chromium"}
        ]

    def test_headless_falls_back_when_channel_unavailable(self, tmp_path):
        spider = DouyinSpider("https://example.com", save_dir=str(tmp_path))
        playwright = _FakePlaywright(fail_channel=True)

        assert spider._launch_browser(playwright) == "browser"
        assert playwright.chromium.calls == [
            {"headless": True, "channel": "chromium"},
            {"headless": True, "args": []},
        ]

    def test_headed_uses_start_maximized(self, tmp_path):
        spider = DouyinSpider(
            "https://example.com", headless=False, save_dir=str(tmp_path)
        )
        playwright = _FakePlaywright()

        spider._launch_browser(playwright)

        assert playwright.chromium.calls == [
            {"headless": False, "args": ["--start-maximized"]}
        ]
