"""Tests for spider modules."""
import pytest
from base_spider import BaseSpider
from douyin_spider import DouyinSpider, extract_url_from_text
from twitter_spider import TwitterSpider
from cli import detect_platform


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

    def test_douyin_referer(self):
        spider = DouyinSpider("https://example.com")
        assert spider.headers["Referer"] == "https://www.douyin.com/"


class TestDetectPlatform:
    def test_detect_douyin(self):
        assert detect_platform("https://v.douyin.com/abc123/") == "douyin"
        assert detect_platform("https://www.douyin.com/video/123") == "douyin"

    def test_detect_twitter_x(self):
        assert detect_platform("https://x.com/user/status/123") == "twitter"

    def test_detect_twitter_com(self):
        assert detect_platform("https://twitter.com/user/status/123") == "twitter"

    def test_detect_unknown_url(self):
        assert detect_platform("https://youtube.com/watch?v=123") == "unknown"

    def test_detect_unknown_text(self):
        assert detect_platform("not a url") == "unknown"

    def test_detect_empty_string(self):
        assert detect_platform("") == "unknown"


class TestBaseSpider:
    def test_init_defaults(self):
        spider = BaseSpider("https://example.com")
        assert spider.url == "https://example.com"
        assert spider.headless is True
        assert spider.video_candidates == []

    def test_init_custom_save_dir(self):
        spider = BaseSpider("https://example.com", save_dir="test_dir")
        assert spider.save_dir == "test_dir"

    def test_init_headless_false(self):
        spider = BaseSpider("https://example.com", headless=False)
        assert spider.headless is False

    def test_headers_contain_user_agent(self):
        spider = BaseSpider("https://example.com")
        assert "User-Agent" in spider.headers
        assert "Referer" in spider.headers

    def test_handle_response_raises(self):
        spider = BaseSpider("https://example.com")
        with pytest.raises(NotImplementedError):
            spider.handle_response(None)

    def test_extract_title_raises(self):
        spider = BaseSpider("https://example.com")
        with pytest.raises(NotImplementedError):
            spider.extract_title(None)


class TestTwitterSpider:
    def test_init(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        assert spider.url == "https://x.com/user/status/123"
        assert spider.DEFAULT_REFERER == "https://x.com/"

    def test_headers_referer(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        assert spider.headers["Referer"] == "https://x.com/"

    def test_find_variants_empty(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        assert spider._find_variants({}) is None

    def test_find_variants_not_found(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        assert spider._find_variants({"data": {"text": "no video here"}}) is None

    def test_find_variants_found(self):
        spider = TwitterSpider("https://x.com/user/status/123")
        data = {
            "data": {
                "tweetResult": {
                    "result": {
                        "legacy": {
                            "extended_entities": {
                                "media": [{
                                    "video_info": {
                                        "variants": [
                                            {"content_type": "video/mp4", "bitrate": 1000, "url": "https://video.twimg.com/test.mp4"},
                                            {"content_type": "application/x-mpegURL", "bitrate": 0, "url": "https://video.twimg.com/test.m3u8"}
                                        ]
                                    }
                                }]
                            }
                        }
                    }
                }
            }
        }
        result = spider._find_variants(data)
        assert result is not None
        assert len(result) == 2
        assert result[0]["content_type"] == "video/mp4"
