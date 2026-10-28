"""Tests for Xiaohongshu parsing and shared URL helpers."""

import json

import pytest

from utils import detect_platform, extract_url_from_text, sanitize_filename
from xhs_spider import (
    XhsError,
    XhsSpider,
    extract_note_id,
    parse_initial_state,
    parse_note,
    parse_setup_state,
)


VIDEO_NOTE = {
    "noteId": "6adc2f9300000000310259e3",
    "type": "video",
    "title": "vlog 游泳",
    "desc": "第一行\n第二行 #tag",
    "imageList": [
        {
            "fileId": "cover123",
            "url": "http://sns-webpic/cover!h5_1080jpg",
            "infoList": [{"url": "http://sns-webpic/cover-dtl"}],
        }
    ],
    "video": {
        "media": {
            "stream": {
                "h265": [
                    {
                        "masterUrl": "http://video/h265.mp4",
                        "size": 200,
                        "backupUrls": ["http://backup/h265.mp4"],
                    }
                ],
                "h264": [
                    {"masterUrl": "http://video/h264-small.mp4", "size": 100},
                    {
                        "masterUrl": "http://video/h264-large.mp4",
                        "size": 300,
                        "backupUrls": ["http://backup/h264.mp4"],
                    },
                ],
            }
        }
    },
}

IMAGE_NOTE = {
    "noteId": "abc123",
    "type": "normal",
    "title": "",
    "desc": "标题行\n正文内容",
    "imageList": [
        {
            "fileId": "f1",
            "url": "http://img/1!h5_1080jpg",
            "infoList": [{"url": "http://img/1-dtl"}],
        },
        {
            "fileId": "",
            "url": "http://img/2!h5_1080jpg",
            "infoList": [{"url": "http://img/2-dtl"}],
        },
        {
            "fileId": "f3",
            "url": "",
            "infoList": [],
        },
    ],
}


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://v.douyin.com/abc/", "douyin"),
        ("https://www.douyin.com/video/123", "douyin"),
        ("https://www.iesdouyin.com/share/video/123", "douyin"),
        ("https://www.xiaohongshu.com/discovery/item/abc?xsec_token=1", "xhs"),
        ("https://www.xiaohongshu.com/explore/abc", "xhs"),
        ("https://xhslink.com/a/abc", "xhs"),
        ("https://example.com/video/123", None),
        ("", None),
    ],
)
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


def test_extract_url_keeps_xsec_token():
    url = (
        "https://www.xiaohongshu.com/discovery/item/6adc2f9300000000310259e3"
        "?source=webshare&xsec_token=AB_ZqMphBHx220BavmGQ875oWuWtzKZ85ySK-gxvVRjxk="
        "&xsec_source=pc_share"
    )
    assert extract_url_from_text(f"看看这个 {url} 好玩") == url


def test_sanitize_filename_removes_illegal_chars():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"


def test_sanitize_filename_truncates_and_strips_trailing_dot():
    assert sanitize_filename("x" * 100, 10) == "x" * 10
    assert sanitize_filename("name...", 50) == "name"
    assert sanitize_filename("", 50) == ""


def test_extract_note_id():
    url = "https://www.xiaohongshu.com/discovery/item/6adc2f9300000000310259e3?xsec_token=x"
    assert extract_note_id(url) == "6adc2f9300000000310259e3"
    assert extract_note_id("https://www.xiaohongshu.com/user/profile/123") == ""


def test_parse_video_note_prefers_h264_and_largest():
    media = parse_note(VIDEO_NOTE)
    assert media.kind == "video"
    assert media.title == "vlog 游泳"
    assert media.video_urls[0] == "http://video/h264-large.mp4"
    assert "http://backup/h264.mp4" in media.video_urls
    assert "http://video/h265.mp4" in media.video_urls
    assert media.image_urls[0][0].startswith("https://ci.xiaohongshu.com/cover123")


def test_parse_image_note_candidates_and_title_fallback():
    media = parse_note(IMAGE_NOTE)
    assert media.kind == "images"
    assert media.title == "标题行"
    assert media.video_urls == []
    assert len(media.image_urls) == 3
    assert media.image_urls[0] == [
        "https://ci.xiaohongshu.com/f1?imageView2/2/format/jpg",
        "http://img/1!h5_1080jpg",
        "http://img/1-dtl",
    ]
    assert media.image_urls[1][0] == "http://img/2!h5_1080jpg"
    assert media.image_urls[2] == ["https://ci.xiaohongshu.com/f3?imageView2/2/format/jpg"]


def test_parse_note_without_title_uses_note_id():
    media = parse_note({"noteId": "n1", "type": "normal", "imageList": []})
    assert media.title == "n1"


def test_parse_note_empty_returns_none():
    assert parse_note({}) is None
    assert parse_note(None) is None


def test_parse_setup_state():
    payload = {"LAUNCHER_SSR_STORE_PAGE_DATA": {"noteData": IMAGE_NOTE}}
    html = (
        "<html><script>window.__SETUP_SERVER_STATE__="
        + json.dumps(payload, ensure_ascii=False)
        + ";</script></html>"
    )
    note = parse_setup_state(html)
    assert note["noteId"] == "abc123"


def test_parse_setup_state_tolerates_undefined():
    html = (
        '<script>window.__SETUP_SERVER_STATE__={"unused": undefined, '
        '"LAUNCHER_SSR_STORE_PAGE_DATA":{"noteData":{"noteId":"n2"}}};</script>'
    )
    note = parse_setup_state(html)
    assert note["noteId"] == "n2"


def test_parse_initial_state_fallback():
    note = {"noteId": "n1", "imageList": [{"url": "http://img/1"}]}
    state = {"note": {"noteDetailMap": {"n1": {"note": note}}}}
    html = (
        "<script>window.__INITIAL_STATE__="
        + json.dumps(state, ensure_ascii=False)
        + ";</script>"
    )
    assert parse_initial_state(html, "n1") == note


def test_parse_initial_state_skips_empty_note():
    state = {"note": {"noteDetailMap": {"undefined": {"note": {}}}}}
    html = (
        "<script>window.__INITIAL_STATE__="
        + json.dumps(state, ensure_ascii=False)
        + ";</script>"
    )
    assert parse_initial_state(html, "undefined") is None


def test_xhs_spider_parse_raises_without_note():
    spider = XhsSpider("https://www.xiaohongshu.com/explore/abc")
    with pytest.raises(XhsError):
        spider.parse("https://www.xiaohongshu.com/explore/abc", "<html></html>")
