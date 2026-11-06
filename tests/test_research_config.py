"""Tests for loading DeepSeek configuration from config.ini."""

import pytest

from research.config import load_config
from research.errors import ResearchConfigError


def write_config(tmp_path, body):
    path = tmp_path / "config.ini"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_CONFIG"):
        monkeypatch.delenv(name, raising=False)


def test_loads_values_from_ini(tmp_path):
    path = write_config(
        tmp_path,
        """[deepseek]
api_key = file-key
base_url = https://api.example.com
connect_timeout = 5
read_timeout = 20
default_count = 3
need_content = true
max_retries = 1
retry_backoff = 0
""",
    )

    config = load_config(path)

    assert config.api_key == "file-key"
    assert config.base_url == "https://api.example.com"
    assert config.connect_timeout == 5.0
    assert config.read_timeout == 20.0
    assert config.default_count == 3
    assert config.default_need_content is True
    assert config.max_retries == 1
    assert config.retry_backoff == 0.0


def test_defaults_when_only_key_is_present(tmp_path):
    path = write_config(tmp_path, "[deepseek]\napi_key = file-key\n")

    config = load_config(path)

    assert config.base_url == "https://api.deepseek.com"
    assert config.connect_timeout == 10.0
    assert config.read_timeout == 60.0
    assert config.default_count == 10
    assert config.default_need_content is False
    assert config.max_retries == 2


def test_env_api_key_and_base_url_override_file(tmp_path, monkeypatch):
    path = write_config(
        tmp_path,
        "[deepseek]\napi_key = file-key\nbase_url = https://file.example.com\n",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.example.com/")

    config = load_config(path)

    assert config.api_key == "env-key"
    assert config.base_url == "https://env.example.com"


def test_env_only_config_without_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    config = load_config(tmp_path / "missing.ini")

    assert config.api_key == "env-key"
    assert config.default_count == 10


def test_deepseek_config_env_selects_file(tmp_path, monkeypatch):
    path = write_config(tmp_path, "[deepseek]\napi_key = selected-key\n")
    monkeypatch.setenv("DEEPSEEK_CONFIG", str(path))

    config = load_config()

    assert config.api_key == "selected-key"


def test_missing_key_has_actionable_message(tmp_path):
    path = write_config(tmp_path, "[deepseek]\napi_key =\n")

    with pytest.raises(ResearchConfigError) as caught:
        load_config(path)

    message = str(caught.value)
    assert "api_key" in message
    assert "DEEPSEEK_API_KEY" in message
    assert str(path) in message


def test_missing_file_without_env_has_actionable_message(tmp_path):
    path = tmp_path / "missing.ini"

    with pytest.raises(ResearchConfigError) as caught:
        load_config(path)

    assert "api_key" in str(caught.value)


def test_malformed_config_has_readable_error(tmp_path):
    path = write_config(tmp_path, "not an ini file\n")

    with pytest.raises(ResearchConfigError, match="无法读取配置文件"):
        load_config(path)


def test_percent_signs_are_not_interpolated(tmp_path):
    path = write_config(
        tmp_path,
        "[deepseek]\napi_key = key-with-%\nbase_url = https://example.com/a%20b\n",
    )

    config = load_config(path)

    assert config.api_key == "key-with-%"
    assert config.base_url == "https://example.com/a%20b"


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://example.com",
        "https://",
        "api.deepseek.com",
        "https://user:pass@example.com",
    ],
)
def test_invalid_base_url_raises(tmp_path, base_url):
    path = write_config(
        tmp_path, f"[deepseek]\napi_key = key\nbase_url = {base_url}\n"
    )

    with pytest.raises(ResearchConfigError, match="base_url"):
        load_config(path)


@pytest.mark.parametrize(
    "line, expected",
    [
        ("default_count = 0", "default_count"),
        ("default_count = 51", "default_count"),
        ("default_count = many", "default_count"),
        ("connect_timeout = 0", "connect_timeout"),
        ("read_timeout = 301", "read_timeout"),
        ("max_retries = 6", "max_retries"),
        ("retry_backoff = -1", "retry_backoff"),
        ("need_content = maybe", "need_content"),
    ],
)
def test_invalid_values_raise(tmp_path, line, expected):
    path = write_config(tmp_path, f"[deepseek]\napi_key = key\n{line}\n")

    with pytest.raises(ResearchConfigError, match=expected):
        load_config(path)


def test_api_key_is_hidden_from_repr(tmp_path):
    path = write_config(tmp_path, "[deepseek]\napi_key = secret-value\n")

    config = load_config(path)

    assert "secret-value" not in repr(config)
