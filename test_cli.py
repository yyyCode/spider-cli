from cli import _collect_urls


def test_collect_urls_skips_invalid_lines(capsys):
    urls = _collect_urls(
        [
            "https://v.douyin.com/a/",
            "no link",
            "https://v.douyin.com/b/",
        ]
    )
    assert urls == [
        "https://v.douyin.com/a/",
        "https://v.douyin.com/b/",
    ]
    assert "第 2 行" in capsys.readouterr().out


def test_collect_urls_reads_file(tmp_path):
    path = tmp_path / "links.txt"
    path.write_text(
        "https://v.douyin.com/a/\n"
        "no link\n"
        "https://v.douyin.com/b/\n",
        encoding="utf-8",
    )
    assert _collect_urls([f"@{path}"]) == [
        "https://v.douyin.com/a/",
        "https://v.douyin.com/b/",
    ]


def test_collect_urls_reports_missing_file(tmp_path, capsys):
    urls = _collect_urls([f"@{tmp_path / 'missing.txt'}"])
    assert urls == []
    assert "无法读取文件" in capsys.readouterr().out
