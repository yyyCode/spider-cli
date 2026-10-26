from config import AppConfig
from douyin_spider import DouyinSpider, extract_url_from_text


def make_spider(tmp_path):
    return DouyinSpider(
        "https://v.douyin.com/abc/",
        session=object(),
        config=AppConfig(save_dir=tmp_path),
        log_callback=lambda message: None,
    )


class FakeResponse:
    def __init__(
        self,
        url,
        *,
        status=200,
        content_type="video/mp4",
        size=2 * 1024 * 1024,
    ):
        self.url = url
        self.status = status
        self.headers = {
            "content-type": content_type,
            "content-length": str(size),
        }


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
        assert extract_url_from_text("") is None

    def test_extract_with_emoji(self):
        text = "😎🔥 https://v.douyin.com/test/ 🔥😎"
        assert extract_url_from_text(text) == "https://v.douyin.com/test/"


class TestParseVideoId:
    def test_long_video_url(self):
        assert (
            DouyinSpider.parse_video_id("https://www.douyin.com/video/7123456789")
            == "7123456789"
        )

    def test_note_url(self):
        assert (
            DouyinSpider.parse_video_id("https://www.douyin.com/note/7123")
            == "7123"
        )

    def test_short_url_returns_none(self):
        assert DouyinSpider.parse_video_id("https://v.douyin.com/abc/") is None

    def test_searches_all_candidates(self):
        assert (
            DouyinSpider.parse_video_id(None, "https://x/video/123?foo=1")
            == "123"
        )


class TestRiskFromText:
    def test_captcha(self):
        assert DouyinSpider.risk_from_text("请完成验证后继续") == "captcha"

    def test_login(self):
        assert DouyinSpider.risk_from_text("登录后查看评论") == "login"

    def test_none(self):
        assert DouyinSpider.risk_from_text("普通页面") is None


class TestSanitizeFilename:
    def test_removes_illegal_chars(self):
        assert DouyinSpider._sanitize_filename("test:file*name?") == "testfilename"

    def test_strips_whitespace(self):
        assert DouyinSpider._sanitize_filename("  spaced  ") == "spaced"


class TestHandleResponse:
    def test_captures_large_video(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse("https://cdn.example.com/a.mp4")
        )
        assert len(spider.video_candidates) == 1
        assert spider.video_candidates[0]["url"] == "https://cdn.example.com/a.mp4"

    def test_ignores_small_file(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse("https://cdn.example.com/ad.mp4", size=1024)
        )
        assert spider.video_candidates == []

    def test_ignores_duplicate_url(self, tmp_path):
        spider = make_spider(tmp_path)
        response = FakeResponse("https://cdn.example.com/a.mp4")
        spider.handle_response(response)
        spider.handle_response(response)
        assert len(spider.video_candidates) == 1

    def test_ignores_non_video(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse(
                "https://www.douyin.com/page",
                content_type="text/html",
            )
        )
        assert spider.video_candidates == []

    def test_ignores_non_200(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.handle_response(
            FakeResponse("https://cdn.example.com/a.mp4", status=304)
        )
        assert spider.video_candidates == []


class TestSelectTarget:
    def test_returns_largest_candidate(self, tmp_path):
        spider = make_spider(tmp_path)
        spider.video_candidates = [
            {"url": "small", "size": 1},
            {"url": "large", "size": 2},
        ]
        assert spider._select_target(None) == "large"

    def test_falls_back_to_video_element(self, tmp_path):
        class FakeVideo:
            def get_attribute(self, name):
                if name == "src":
                    return "https://cdn.example.com/fallback.mp4"
                return None

            def query_selector_all(self, selector):
                return []

        class FakePage:
            def query_selector(self, selector):
                return FakeVideo()

        spider = make_spider(tmp_path)
        assert (
            spider._select_target(FakePage())
            == "https://cdn.example.com/fallback.mp4"
        )
