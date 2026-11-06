"""Tests for the DeepSeek Search/Fetch client."""

import json

import pytest
import requests

from research.client import DeepSeekClient
from research.config import DeepSeekConfig
from research.errors import ResearchError, ResearchValidationError


class FakeResponse:
    def __init__(self, status_code=200, data=None, headers=None, json_error=None):
        self.status_code = status_code
        self.data = data
        self.headers = headers or {}
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_config(**overrides):
    values = {
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
        "connect_timeout": 1.0,
        "read_timeout": 2.0,
        "default_count": 10,
        "default_need_content": False,
        "max_retries": 0,
        "retry_backoff": 0.0,
    }
    values.update(overrides)
    return DeepSeekConfig(**values)


def make_client(responses, **config):
    session = FakeSession(responses)
    return DeepSeekClient(make_config(**config), session=session), session


def test_search_sends_documented_payload_and_auth():
    results = [{"title": "DeepSeek V4", "url": "https://example.com"}]
    client, session = make_client([FakeResponse(data={"results": results})])

    returned = client.search(
        "DeepSeek V4",
        count=5,
        need_content=True,
        ori_question="DeepSeek V4 什么时候发布？",
        localization="1.2.3.4",
    )

    assert returned == results
    call = session.calls[0]
    assert call["url"] == "https://api.deepseek.com/v1/tools/search"
    assert call["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert call["timeout"] == (1.0, 2.0)
    assert call["json"] == {
        "query": "DeepSeek V4",
        "count": 5,
        "need_content": True,
        "ori_question": "DeepSeek V4 什么时候发布？",
        "localization": "1.2.3.4",
    }


def test_search_uses_config_defaults():
    client, session = make_client(
        [FakeResponse(data={"results": []})],
        default_count=7,
        default_need_content=True,
    )

    client.search("  DeepSeek  ")

    assert session.calls[0]["json"] == {
        "query": "DeepSeek",
        "count": 7,
        "need_content": True,
    }


def test_search_omits_empty_optional_fields():
    client, session = make_client([FakeResponse(data={"results": []})])

    client.search("query", ori_question="  ", localization="")

    assert "ori_question" not in session.calls[0]["json"]
    assert "localization" not in session.calls[0]["json"]


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_search_rejects_blank_query(query):
    client, session = make_client([])

    with pytest.raises(ResearchValidationError, match="搜索词"):
        client.search(query)

    assert session.calls == []


def test_search_rejects_query_over_128_chars():
    client, _ = make_client([])

    with pytest.raises(ResearchValidationError, match="128"):
        client.search("字" * 129)


@pytest.mark.parametrize("count", [0, 51, -1, "many"])
def test_search_rejects_invalid_count(count):
    client, _ = make_client([])

    with pytest.raises(ResearchValidationError, match="结果数量"):
        client.search("query", count=count)


def test_search_rejects_invalid_localization():
    client, _ = make_client([])

    with pytest.raises(ResearchValidationError, match="IP"):
        client.search("query", localization="not-an-ip")


def test_search_rejects_long_ori_question():
    client, _ = make_client([])

    with pytest.raises(ResearchValidationError, match="128"):
        client.search("query", ori_question="问" * 129)


def test_search_rejects_malformed_results():
    client, _ = make_client([FakeResponse(data={"results": "nope"})])

    with pytest.raises(ResearchError) as caught:
        client.search("query")

    assert caught.value.status_code == 502


def test_fetch_sends_url_and_returns_document():
    client, session = make_client(
        [FakeResponse(data={"title": "Example", "content": "# Heading"})]
    )

    result = client.fetch("https://example.com/article")

    assert result == {"title": "Example", "content": "# Heading"}
    assert session.calls[0]["url"] == "https://api.deepseek.com/v1/tools/fetch"
    assert session.calls[0]["json"] == {"url": "https://example.com/article"}


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "example.com/article",
        "ftp://example.com/article",
        "file:///etc/passwd",
        "https://",
        "https://user:pass@example.com/article",
        "https://example.com/a b",
    ],
)
def test_fetch_rejects_invalid_urls(url):
    client, session = make_client([])

    with pytest.raises(ResearchValidationError, match="网页地址"):
        client.fetch(url)

    assert session.calls == []


def test_fetch_rejects_url_over_8192_chars():
    client, _ = make_client([])
    url = "https://example.com/" + "a" * 8200

    with pytest.raises(ResearchValidationError, match="8192"):
        client.fetch(url)


def test_fetch_normalises_missing_fields():
    client, _ = make_client([FakeResponse(data={"title": None})])

    assert client.fetch("https://example.com") == {"title": "", "content": ""}


def test_fetch_rejects_non_object_response():
    client, _ = make_client([FakeResponse(data=["not", "an", "object"])])

    with pytest.raises(ResearchError) as caught:
        client.fetch("https://example.com")

    assert caught.value.status_code == 502


def test_400_uses_upstream_message():
    client, _ = make_client(
        [
            FakeResponse(
                status_code=400,
                data={"error": {"message": "'count' must be between 1 and 50"}},
            )
        ]
    )

    with pytest.raises(ResearchError) as caught:
        client.search("query")

    assert caught.value.status_code == 400
    assert caught.value.message == "'count' must be between 1 and 50"


@pytest.mark.parametrize(
    "status, fragment",
    [
        (401, "API Key"),
        (402, "余额"),
        (403, "安全策略"),
        (404, "正文"),
        (413, "大小限制"),
        (429, "频繁"),
        (500, "内部错误"),
        (504, "超时"),
    ],
)
def test_error_statuses_have_actionable_messages(status, fragment):
    client, _ = make_client([FakeResponse(status_code=status, data={})])

    with pytest.raises(ResearchError) as caught:
        client.search("query")

    assert fragment in caught.value.message
    expected_status = status if status < 500 else 502
    assert caught.value.status_code == expected_status


def test_unknown_4xx_status_is_passed_through():
    client, _ = make_client([FakeResponse(status_code=418, data={})])

    with pytest.raises(ResearchError) as caught:
        client.search("query")

    assert caught.value.status_code == 418
    assert "418" in caught.value.message


def test_retries_429_then_succeeds():
    client, session = make_client(
        [
            FakeResponse(status_code=429),
            FakeResponse(data={"results": [{"title": "ok"}]}),
        ],
        max_retries=1,
    )

    assert client.search("query") == [{"title": "ok"}]
    assert len(session.calls) == 2


def test_retries_5xx_then_succeeds():
    client, session = make_client(
        [
            FakeResponse(status_code=503),
            FakeResponse(data={"results": []}),
        ],
        max_retries=1,
    )

    assert client.search("query") == []
    assert len(session.calls) == 2


def test_retry_after_header_controls_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr("research.client.time.sleep", sleeps.append)
    client, _ = make_client(
        [
            FakeResponse(status_code=429, headers={"Retry-After": "2"}),
            FakeResponse(data={"results": []}),
        ],
        max_retries=1,
        retry_backoff=0.5,
    )

    client.search("query")

    assert sleeps == [2.0]


def test_timeout_retries_then_raises_504(monkeypatch):
    monkeypatch.setattr("research.client.time.sleep", lambda seconds: None)
    client, session = make_client(
        [requests.Timeout(), requests.Timeout()], max_retries=1
    )

    with pytest.raises(ResearchError) as caught:
        client.search("query")

    assert caught.value.status_code == 504
    assert len(session.calls) == 2


def test_connection_error_raises_502():
    client, _ = make_client([requests.ConnectionError()])

    with pytest.raises(ResearchError) as caught:
        client.search("query")

    assert caught.value.status_code == 502
    assert "无法连接" in caught.value.message


def test_invalid_json_raises_502():
    client, _ = make_client([FakeResponse(json_error=json.JSONDecodeError("x", "", 0))])

    with pytest.raises(ResearchError) as caught:
        client.search("query")

    assert caught.value.status_code == 502
    assert "解析" in caught.value.message


def test_trailing_slash_in_base_url_is_normalised():
    client, session = make_client(
        [FakeResponse(data={"results": []})], base_url="https://api.example.com/"
    )

    client.search("query")

    assert session.calls[0]["url"] == "https://api.example.com/v1/tools/search"
