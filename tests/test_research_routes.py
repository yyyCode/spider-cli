"""Tests for the research page tab and its API routes."""

from fastapi.testclient import TestClient

from research.config import DeepSeekConfig
from research.errors import ResearchConfigError, ResearchError
from web import app as web_app
from web import research_routes


class FakeClient:
    def __init__(self, results=None, fetch_result=None, error=None):
        self.results = results if results is not None else []
        self.fetch_result = fetch_result or {"title": "", "content": ""}
        self.error = error
        self.search_args = None
        self.fetch_arg = None

    def search(
        self,
        query,
        count=None,
        need_content=None,
        ori_question=None,
        localization=None,
    ):
        self.search_args = {
            "query": query,
            "count": count,
            "need_content": need_content,
            "ori_question": ori_question,
            "localization": localization,
        }
        if self.error:
            raise self.error
        return self.results

    def fetch(self, url):
        self.fetch_arg = url
        if self.error:
            raise self.error
        return self.fetch_result


def make_client():
    return TestClient(web_app.app)


def use_fake(monkeypatch, fake):
    monkeypatch.setattr(research_routes, "get_client", lambda: fake)


def test_old_research_url_redirects_to_workbench_tab():
    with make_client() as client:
        response = client.get("/research", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/#research"


def test_home_page_exposes_both_tools_as_tabs():
    with make_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "视频接收台" in response.text
    assert "网页搜索" in response.text
    assert 'id="tool-video"' in response.text
    assert 'id="tool-research"' in response.text
    assert 'id="panel-video"' in response.text
    assert 'id="panel-research"' in response.text


def test_research_panel_markup_is_available():
    with make_client() as client:
        response = client.get("/static/research.html")

    assert response.status_code == 200
    assert "研究台" in response.text
    assert "DeepSeek" in response.text


def test_status_reports_configured_without_exposing_key(monkeypatch):
    config = DeepSeekConfig(
        api_key="secret-key",
        base_url="https://api.deepseek.com",
        default_count=7,
        default_need_content=True,
    )
    monkeypatch.setattr(research_routes, "load_config", lambda: config)

    with make_client() as client:
        response = client.get("/api/research/status")

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "base_url": "https://api.deepseek.com",
        "default_count": 7,
        "default_need_content": True,
    }
    assert "secret-key" not in response.text


def test_status_reports_missing_config(monkeypatch):
    def fail():
        raise ResearchConfigError("未配置 DeepSeek API Key。")

    monkeypatch.setattr(research_routes, "load_config", fail)

    with make_client() as client:
        response = client.get("/api/research/status")

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "message": "未配置 DeepSeek API Key。",
    }


def test_search_returns_results_and_forwards_fields(monkeypatch):
    fake = FakeClient(results=[{"title": "Result", "url": "https://example.com"}])
    use_fake(monkeypatch, fake)

    with make_client() as client:
        response = client.post(
            "/api/research/search",
            json={
                "query": "DeepSeek V4",
                "count": 5,
                "need_content": True,
                "ori_question": "原始问题",
                "localization": "1.2.3.4",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "results": [{"title": "Result", "url": "https://example.com"}]
    }
    assert fake.search_args == {
        "query": "DeepSeek V4",
        "count": 5,
        "need_content": True,
        "ori_question": "原始问题",
        "localization": "1.2.3.4",
    }


def test_search_forwards_none_for_omitted_options(monkeypatch):
    fake = FakeClient()
    use_fake(monkeypatch, fake)

    with make_client() as client:
        response = client.post("/api/research/search", json={"query": "query"})

    assert response.status_code == 200
    assert fake.search_args == {
        "query": "query",
        "count": None,
        "need_content": None,
        "ori_question": None,
        "localization": None,
    }


def test_search_maps_upstream_error_status(monkeypatch):
    fake = FakeClient(error=ResearchError("账户余额不足。", 402))
    use_fake(monkeypatch, fake)

    with make_client() as client:
        response = client.post("/api/research/search", json={"query": "query"})

    assert response.status_code == 402
    assert response.json() == {"detail": "账户余额不足。"}


def test_search_maps_missing_config_to_503(monkeypatch):
    def fail():
        raise ResearchConfigError("未配置 DeepSeek API Key。")

    monkeypatch.setattr(research_routes, "get_client", fail)

    with make_client() as client:
        response = client.post("/api/research/search", json={"query": "query"})

    assert response.status_code == 503
    assert "API Key" in response.json()["detail"]


def test_search_unexpected_error_returns_500(monkeypatch):
    fake = FakeClient(error=RuntimeError("boom"))
    use_fake(monkeypatch, fake)

    with make_client() as client:
        response = client.post("/api/research/search", json={"query": "query"})

    assert response.status_code == 500
    assert response.json()["detail"] == "搜索服务内部错误，请查看服务端日志。"


def test_search_missing_query_returns_422():
    with make_client() as client:
        response = client.post("/api/research/search", json={})

    assert response.status_code == 422


def test_fetch_returns_document(monkeypatch):
    fake = FakeClient(
        fetch_result={"title": "Example", "content": "# Heading\n\nBody"}
    )
    use_fake(monkeypatch, fake)

    with make_client() as client:
        response = client.post(
            "/api/research/fetch", json={"url": "https://example.com/article"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "title": "Example",
        "content": "# Heading\n\nBody",
    }
    assert fake.fetch_arg == "https://example.com/article"


def test_fetch_maps_upstream_error_status(monkeypatch):
    fake = FakeClient(error=ResearchError("目标网页没有可用正文。", 404))
    use_fake(monkeypatch, fake)

    with make_client() as client:
        response = client.post(
            "/api/research/fetch", json={"url": "https://example.com/missing"}
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "目标网页没有可用正文。"}


def test_fetch_missing_url_returns_422():
    with make_client() as client:
        response = client.post("/api/research/fetch", json={})

    assert response.status_code == 422
