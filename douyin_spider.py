import re
from base_spider import BaseSpider


class DouyinSpider(BaseSpider):
    """Douyin-specific spider, inheriting browser lifecycle and download logic from BaseSpider."""

    DEFAULT_REFERER = "https://www.douyin.com/"

    def handle_response(self, response):
        """监控抖音网络响应，捕获视频流地址。"""
        try:
            if response.status == 200 and (
                    'video/mp4' in response.headers.get('content-type', '')
                    or '.mp4' in response.url):
                content_length = int(response.headers.get('content-length', 0))
                url = response.url

                if content_length > self.MIN_VIDEO_SIZE:
                    self.log(f"捕获视频流: 大小={content_length/1024/1024:.2f}MB, URL={url[:60]}...")
                    self.video_candidates.append({
                        'url': url,
                        'size': content_length
                    })
                else:
                    self.log(f"忽略小文件(可能是广告): 大小={content_length/1024}KB, URL={url[:60]}...")
        except Exception:
            pass

    def extract_title(self, page):
        """提取抖音视频标题，对'抖音'页面回退到 .desc 定位器。"""
        title = page.title()
        if not title or title == "抖音":
            try:
                title = page.locator('.desc').first.inner_text()
            except Exception:
                pass
        return title


def extract_url_from_text(text):
    """
    从混合文本中提取 URL
    """
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    if urls:
        return urls[0]
    return None
