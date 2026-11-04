"""Tests for the FastAPI endpoints."""

from fastapi.testclient import TestClient

from web import app as web_app
from web.service import DownloadedFile


def make_client():
    return TestClient(web_app.app)


def test_health():
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_serves_html():
    with make_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "视频下载器" in response.text


def test_download_returns_file_and_cleans_temp(monkeypatch, tmp_path):
    temp_dir = tmp_path / "download"
    temp_dir.mkdir()
    target = temp_dir / "测试视频.mp4"
    target.write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(
        web_app,
        "download_video",
        lambda raw: DownloadedFile(
            path=str(target),
            filename=target.name,
            temp_dir=str(temp_dir),
        ),
    )

    with make_client() as client:
        response = client.post(
            "/api/download", json={"url": "https://v.douyin.com/abc/"}
        )

    assert response.status_code == 200
    assert response.content == b"fake-video-bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert "attachment" in response.headers["content-disposition"]
    assert "mp4" in response.headers["content-disposition"]
    assert not temp_dir.exists()


def test_download_invalid_url_returns_400():
    with make_client() as client:
        response = client.post("/api/download", json={"url": "这里没有链接"})

    assert response.status_code == 400
    assert "链接" in response.json()["detail"]


def test_download_unsupported_platform_returns_400():
    with make_client() as client:
        response = client.post(
            "/api/download", json={"url": "https://example.com/video"}
        )

    assert response.status_code == 400
    assert "抖音" in response.json()["detail"]


def test_download_missing_url_returns_422():
    with make_client() as client:
        response = client.post("/api/download", json={})

    assert response.status_code == 422


def test_download_error_maps_to_status(monkeypatch):
    def raise_error(raw):
        raise web_app.WebDownloadError("上游解析失败", 502)

    monkeypatch.setattr(web_app, "download_video", raise_error)

    with make_client() as client:
        response = client.post(
            "/api/download", json={"url": "https://v.douyin.com/abc/"}
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "上游解析失败"}
