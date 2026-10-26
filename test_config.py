import json

from config import AppConfig, load_config, save_config


def test_load_config_creates_default_file(tmp_path):
    path = tmp_path / "config.json"
    config = load_config(path, cwd=tmp_path)
    assert path.exists()
    assert config.save_dir == (tmp_path / "videos").resolve()
    assert config.headless is False
    assert config.page_delay == (4.0, 9.0)
    assert config.max_retries == 3


def test_load_config_reads_overrides(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "save_dir": "downloads",
                "headless": True,
                "page_delay": [1, 2],
                "download_delay": [0.5, 1.5],
                "max_retries": 5,
                "cooldown_seconds": 30,
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path, cwd=tmp_path)
    assert config.save_dir == (tmp_path / "downloads").resolve()
    assert config.headless is True
    assert config.page_delay == (1.0, 2.0)
    assert config.download_delay == (0.5, 1.5)
    assert config.max_retries == 5
    assert config.cooldown_seconds == 30.0


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "page_delay": ["x", 2],
                "download_delay": [5, 1],
                "max_retries": "many",
                "headless": "yes",
                "chunk_size": -1,
                "human_behavior": "true",
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path, cwd=tmp_path)
    assert config.page_delay == (4.0, 9.0)
    assert config.download_delay == (1.0, 2.0)
    assert config.max_retries == 3
    assert config.headless is False
    assert config.chunk_size == 65536
    assert config.human_behavior is True


def test_save_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig(save_dir=tmp_path / "videos", headless=True)
    save_config(config, path)
    loaded = load_config(path, cwd=tmp_path)
    assert loaded.headless is True
    assert loaded.save_dir == (tmp_path / "videos").resolve()
