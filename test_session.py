from pathlib import Path

from config import AppConfig
from session import BrowserSession


def test_is_logged_in_cookies():
    assert BrowserSession.is_logged_in_cookies([{"name": "sessionid"}]) is True
    assert BrowserSession.is_logged_in_cookies([{"name": "sessionid_ss"}]) is True
    assert BrowserSession.is_logged_in_cookies([{"name": "ttwid"}]) is False
    assert BrowserSession.is_logged_in_cookies([]) is False


def test_stealth_path_points_to_project_file(tmp_path):
    session = BrowserSession(
        AppConfig(save_dir=tmp_path),
        profile_dir=tmp_path / "profile",
    )
    assert session._stealth_path() == Path(__file__).resolve().parent / "stealth.min.js"
