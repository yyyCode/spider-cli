# Twitter/X Video Spider - Design Spec

## Overview

Extend the existing Douyin video spider to support Twitter/X video links, with an
extensible architecture that makes adding future platforms straightforward.

## Architecture

```
BaseSpider (browser lifecycle, stealth injection, download)
    ├── DouyinSpider (network-intercept video/mp4 responses)
    └── TwitterSpider (network-intercept Twitter GraphQL API responses)
```

CLI layer: `detect_platform(url)` routes to the correct spider by domain.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `base_spider.py` | New | Common browser, stealth, download logic extracted from DouyinSpider |
| `douyin_spider.py` | Modify | Inherit BaseSpider, keep only Douyin-specific response handling |
| `twitter_spider.py` | New | Twitter spider: intercept API responses, parse JSON, extract video |
| `cli.py` | Modify | Generic branding, add `detect_platform()`, route to correct spider |
| `test_spider.py` | Modify | Add tests for BaseSpider, TwitterSpider, detect_platform |

## BaseSpider

Common functionality shared by all platform spiders:

- Playwright browser launch (`chromium.launch`)
- Browser context creation with UA and viewport
- `stealth.min.js` injection
- Network response event binding (subclass provides the handler)
- Video download via `requests` with streaming to file
- Filename sanitization, directory creation, logging
- Constants: `MIN_VIDEO_SIZE`, `CHUNK_SIZE`, `PAGE_TIMEOUT`, etc.

Subclasses override:
- `handle_response(self, response)` — platform-specific network interception
- `extract_title(self, page)` — platform-specific title extraction
- `headers` property — platform-specific HTTP headers (Referer)

## TwitterSpider

### Video URL Extraction

Intercept XHR/fetch responses to Twitter's internal GraphQL API:

```
URL pattern: */i/api/graphql/*/TweetDetail
         or: */i/api/graphql/*/TweetResultByRestId

JSON path:
  data.tweetResult.result.legacy.extended_entities.media[0]
    .video_info.variants[]

Filter: variant.content_type == "video/mp4"
Select: highest bitrate variant
Result: variant.url (direct MP4 link)
```

### Title Extraction

From `<meta property="og:title" content="...">` which contains the tweet text,
falling back to `page.title()`.

### Headers

- `User-Agent`: same as Douyin (Chrome 120)
- `Referer`: `https://x.com/`

## CLI Changes

- App title changed from "抖音视频爬虫" to "社交媒体视频爬虫"
- New `detect_platform(url)` function: matches domain to platform name
- URL routing: `douyin.com` → `DouyinSpider`, `x.com|twitter.com` → `TwitterSpider`
- Unknown domains show error message instead of silently failing
- Menu structure, TUI navigation, save path config are unchanged

## Error Handling

- Unknown platform: CLI shows "未识别的平台链接" and returns to menu
- No video found: spider logs reason and exits gracefully (same as current behavior)
- Network/graphql errors: caught and logged, spider exits without crashing
- Twitter API response structure changes: defensive `.get()` with None defaults

## Testing

- `test_detect_platform` — douyin, twitter, unknown URLs
- `test_base_spider_init` — base class constructor and defaults
- `test_twitter_spider_init` — constructor sets correct headers/Referer
- Existing DouyinSpider and extract_url_from_text tests remain unchanged

## Non-Goals

- Twitter login / authenticated access
- HLS/m3u8 stream downloading (yt-dlp)
- GUI mode
- Other platforms (Instagram, YouTube, etc.) — but architecture supports adding them
