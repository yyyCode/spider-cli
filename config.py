from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_DIR = Path.home() / ".douyin-spider"
CONFIG_PATH = APP_DIR / "config.json"
PROFILE_DIR = APP_DIR / "profile"
STATE_PATH = APP_DIR / "state.json"

DEFAULT_PAGE_DELAY = (4.0, 9.0)
DEFAULT_DOWNLOAD_DELAY = (1.0, 2.0)


@dataclass
class AppConfig:
    save_dir: Path
    headless: bool = False
    page_delay: tuple[float, float] = DEFAULT_PAGE_DELAY
    download_delay: tuple[float, float] = DEFAULT_DOWNLOAD_DELAY
    cooldown_seconds: float = 90.0
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 8.0
    page_timeout_ms: int = 60000
    video_wait_timeout_ms: int = 15000
    login_timeout_seconds: float = 180.0
    min_video_size: int = 1048576
    chunk_size: int = 65536
    human_behavior: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "save_dir": str(self.save_dir),
            "headless": self.headless,
            "page_delay": list(self.page_delay),
            "download_delay": list(self.download_delay),
            "cooldown_seconds": self.cooldown_seconds,
            "max_retries": self.max_retries,
            "backoff_base": self.backoff_base,
            "backoff_max": self.backoff_max,
            "page_timeout_ms": self.page_timeout_ms,
            "video_wait_timeout_ms": self.video_wait_timeout_ms,
            "login_timeout_seconds": self.login_timeout_seconds,
            "min_video_size": self.min_video_size,
            "chunk_size": self.chunk_size,
            "human_behavior": self.human_behavior,
        }


def _absolute_save_dir(raw: Any, cwd: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        return (cwd / "videos").resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def _pair(raw: Any, default: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return default
    try:
        low, high = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return default
    if low < 0 or high < low:
        return default
    return (low, high)


def _number(raw: Any, default: float, *, minimum: float = 0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _integer(raw: Any, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _boolean(raw: Any, default: bool) -> bool:
    return raw if isinstance(raw, bool) else default


def load_config(
    path: Path = CONFIG_PATH,
    *,
    cwd: Path | None = None,
    write_if_missing: bool = True,
) -> AppConfig:
    cwd = Path(cwd or Path.cwd())
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("配置根节点必须是对象")
            data = loaded
        except (OSError, ValueError) as exc:
            print(f"[Config] 读取配置失败，使用默认值: {exc}")
            data = {}

    config = AppConfig(
        save_dir=_absolute_save_dir(data.get("save_dir"), cwd),
        headless=_boolean(data.get("headless"), False),
        page_delay=_pair(data.get("page_delay"), DEFAULT_PAGE_DELAY),
        download_delay=_pair(data.get("download_delay"), DEFAULT_DOWNLOAD_DELAY),
        cooldown_seconds=_number(data.get("cooldown_seconds"), 90.0),
        max_retries=_integer(data.get("max_retries"), 3),
        backoff_base=_number(data.get("backoff_base"), 1.0),
        backoff_max=_number(data.get("backoff_max"), 8.0),
        page_timeout_ms=_integer(data.get("page_timeout_ms"), 60000),
        video_wait_timeout_ms=_integer(data.get("video_wait_timeout_ms"), 15000),
        login_timeout_seconds=_number(data.get("login_timeout_seconds"), 180.0),
        min_video_size=_integer(data.get("min_video_size"), 1048576),
        chunk_size=_integer(data.get("chunk_size"), 65536),
        human_behavior=_boolean(data.get("human_behavior"), True),
    )

    if write_if_missing and not path.exists():
        save_config(config, path)
    return config


def save_config(config: AppConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
