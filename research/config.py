"""Load DeepSeek credentials and defaults from ``config.ini``."""

import os
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .errors import ResearchConfigError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.ini"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.ini"


@dataclass(frozen=True)
class DeepSeekConfig:
    """Runtime settings. The API key is excluded from ``repr``."""

    api_key: str = field(repr=False)
    base_url: str = "https://api.deepseek.com"
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    default_count: int = 10
    default_need_content: bool = False
    max_retries: int = 2
    retry_backoff: float = 0.5


def resolve_config_path(path=None):
    """Return the configured file path, honouring ``DEEPSEEK_CONFIG``."""

    if path is not None:
        return Path(path)
    return Path(os.environ.get("DEEPSEEK_CONFIG") or DEFAULT_CONFIG_PATH)


def _read_parser(config_path):
    parser = ConfigParser(interpolation=None)
    if not config_path.exists():
        return parser
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, UnicodeError, ConfigParserError) as exc:
        raise ResearchConfigError(f"无法读取配置文件 {config_path}：{exc}") from exc
    return parser


def _number(parser, key, fallback, minimum, maximum, label):
    raw = parser.get("deepseek", key, fallback=str(fallback))
    try:
        value = float(raw) if isinstance(fallback, float) else int(raw)
    except ValueError as exc:
        raise ResearchConfigError(f"配置项 {label} 必须是数字，当前为 {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ResearchConfigError(
            f"配置项 {label} 必须在 {minimum} 到 {maximum} 之间，当前为 {value}"
        )
    return value


def load_config(path=None):
    """Read and validate the DeepSeek configuration.

    Environment variables ``DEEPSEEK_API_KEY`` and ``DEEPSEEK_BASE_URL``
    override values from the file. A blank key is a configuration error,
    because every request requires it.
    """

    config_path = resolve_config_path(path)
    parser = _read_parser(config_path)

    api_key = os.environ.get("DEEPSEEK_API_KEY") or parser.get(
        "deepseek", "api_key", fallback=""
    )
    api_key = api_key.strip()
    base_url = (
        os.environ.get("DEEPSEEK_BASE_URL")
        or parser.get("deepseek", "base_url", fallback="https://api.deepseek.com")
    ).strip()

    if not api_key:
        raise ResearchConfigError(
            f"未配置 DeepSeek API Key。请在 {config_path} 的 [deepseek] 中填写 "
            "api_key，或设置环境变量 DEEPSEEK_API_KEY。"
        )
    try:
        base_parts = urlsplit(base_url)
    except ValueError as exc:
        raise ResearchConfigError("配置项 base_url 格式不正确。") from exc
    if (
        base_parts.scheme not in ("http", "https")
        or not base_parts.hostname
        or base_parts.username
        or base_parts.password
    ):
        raise ResearchConfigError(
            "配置项 base_url 必须是包含主机名、且不带用户名密码的 http:// 或 https:// 地址。"
        )

    try:
        need_content = parser.getboolean(
            "deepseek", "need_content", fallback=False
        )
    except ValueError as exc:
        raise ResearchConfigError("配置项 need_content 必须是 true 或 false。") from exc

    return DeepSeekConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        connect_timeout=_number(
            parser, "connect_timeout", 10.0, 1, 120, "connect_timeout"
        ),
        read_timeout=_number(parser, "read_timeout", 60.0, 1, 300, "read_timeout"),
        default_count=_number(parser, "default_count", 10, 1, 50, "default_count"),
        default_need_content=need_content,
        max_retries=_number(parser, "max_retries", 2, 0, 5, "max_retries"),
        retry_backoff=_number(parser, "retry_backoff", 0.5, 0, 10, "retry_backoff"),
    )
