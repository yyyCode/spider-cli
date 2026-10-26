from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from batch import BatchRunner, StateStore
from config import load_config, save_config
from douyin_spider import extract_url_from_text
from session import BrowserSession

import os
import sys
import traceback

T = TypeVar("T")


def _tui_available() -> bool:
    try:
        import prompt_toolkit  # noqa: F401

        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _menu_tui(save_dir: str) -> str:
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    items = [
        ("login", "登录 / 检查登录状态"),
        ("batch", "开始批量爬取"),
        ("retry_failed", "重试失败项"),
        ("set_path", "配置下载路径"),
        ("quit", "退出"),
    ]
    state = {"index": 0}

    def _render():
        lines = []
        lines.append(("class:cwd", f"{os.getcwd()}\n\n"))
        lines.append(("class:muted", f"当前下载路径: {save_dir}\n\n"))
        lines.append(("class:muted", "↑↓ 选择 · Enter 确认 · Esc 退出\n\n"))
        for i, (_, label) in enumerate(items, start=1):
            if (i - 1) == state["index"]:
                lines.append(("class:selected", f"> {i}. {label}\n"))
            else:
                lines.append(("", f"  {i}. {label}\n"))
        return lines

    control = FormattedTextControl(
        text=_render,
        focusable=True,
        show_cursor=False,
    )
    root = Window(content=control, always_hide_cursor=True)
    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        state["index"] = max(0, state["index"] - 1)
        event.app.invalidate()

    @kb.add("down")
    def _down(event):
        state["index"] = min(len(items) - 1, state["index"] + 1)
        event.app.invalidate()

    @kb.add("enter")
    def _enter(event):
        event.app.exit(result=items[state["index"]][0])

    @kb.add("escape")
    def _esc(event):
        event.app.exit(result="quit")

    @kb.add("j")
    def _j(event):
        state["index"] = min(len(items) - 1, state["index"] + 1)
        event.app.invalidate()

    @kb.add("k")
    def _k(event):
        state["index"] = max(0, state["index"] - 1)
        event.app.invalidate()

    style = Style.from_dict(
        {
            "cwd": "bold",
            "muted": "fg:#888888",
            "selected": "bold",
        }
    )

    app = Application(
        layout=Layout(root),
        key_bindings=kb,
        style=style,
        full_screen=False,
    )
    result = app.run()
    return result or "quit"


def _input_tui(prompt_text: str, default: str = "") -> str:
    from prompt_toolkit import prompt

    try:
        text = prompt(f"{prompt_text}\n> ", default=default or "")
        return (text or "").strip()
    except (KeyboardInterrupt, EOFError):
        return ""


def _menu_plain(save_dir: str) -> str:
    print("\n当前下载路径:", save_dir)
    print("请选择操作：")
    print("  1. 登录 / 检查登录状态")
    print("  2. 开始批量爬取")
    print("  3. 重试失败项")
    print("  4. 配置下载路径")
    print("  q. 退出")
    print("请输入选项: ", end="", flush=True)
    choice = sys.stdin.readline().strip()

    if not choice:
        return ""
    if choice.lower() in ["q", "quit", "exit"]:
        return "quit"
    return {
        "1": "login",
        "2": "batch",
        "3": "retry_failed",
        "4": "set_path",
    }.get(choice, "invalid")


def _try_tui(
    use_tui_ref: list[bool],
    tui_func: Callable[[], T],
    plain_func: Callable[[], T],
    fallback_msg: str,
) -> T:
    if use_tui_ref[0]:
        try:
            return tui_func()
        except Exception as exc:
            print(f"提示：{fallback_msg}。原因：{exc}")
            use_tui_ref[0] = False
    return plain_func()


def _plain_input(prompt_text: str, prefix: str = "") -> str:
    print(f"{prefix}{prompt_text} ", end="", flush=True)
    return sys.stdin.readline().strip()


def _read_links_tui() -> list[str]:
    print("逐行粘贴链接或分享文本，空行结束；输入 @文件路径 可批量导入。")
    lines = []
    while True:
        line = _input_tui("链接/文本（空行结束）:")
        if not line:
            break
        lines.append(line)
    return lines


def _read_links_plain() -> list[str]:
    print("逐行粘贴链接或分享文本，空行结束；输入 @文件路径 可批量导入。")
    lines = []
    while True:
        line = sys.stdin.readline().strip()
        if not line:
            break
        lines.append(line)
    return lines


def _collect_urls(lines: list[str]) -> list[str]:
    urls: list[str] = []
    for index, line in enumerate(lines, start=1):
        if line.startswith("@"):
            path = Path(line[1:].strip()).expanduser()
            try:
                file_lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                print(f"第 {index} 行：无法读取文件 {path}: {exc}")
                continue
            for file_line in file_lines:
                url = extract_url_from_text(file_line)
                if url:
                    urls.append(url)
            continue

        url = extract_url_from_text(line)
        if url:
            urls.append(url)
        else:
            print(f"第 {index} 行未识别到链接，已跳过")
    return urls


def main() -> None:
    print("=" * 60)
    print("抖音视频爬虫命令行版 v1.1")
    print("功能：登录态复用、批量爬取、限频重试、断点续爬")
    use_tui = _tui_available()
    if use_tui:
        print("操作：↑↓ 选择，Enter 确认；Esc 退出。")
        print('提示：在"输入路径/链接"时，使用 Ctrl+C 取消并返回菜单。')
    else:
        print("操作：启动后选择功能。输入 'q' 退出。")
    print("=" * 60)

    config = load_config()
    config.save_dir.mkdir(parents=True, exist_ok=True)
    save_dir = str(config.save_dir)
    store = StateStore()
    store.load()
    session = BrowserSession(config)
    use_tui_ref = [use_tui]

    try:
        while True:
            try:
                action = _try_tui(
                    use_tui_ref,
                    lambda: _menu_tui(save_dir),
                    lambda: _menu_plain(save_dir),
                    "交互式菜单不可用，已回退到数字菜单",
                )

                if not action:
                    continue

                if action == "quit":
                    print("程序已退出。")
                    break

                if action == "invalid":
                    print("无效选项，请重新选择。")
                    continue

                if action == "login":
                    try:
                        session.start()
                    except RuntimeError as exc:
                        print(exc)
                        continue
                    if session.ensure_login(
                        lambda message: print(message)
                    ):
                        print("登录状态：已登录")
                    else:
                        print(
                            "未检测到登录态。请使用有头模式并重新执行登录。"
                        )
                    continue

                if action == "set_path":
                    new_dir = _try_tui(
                        use_tui_ref,
                        lambda: _input_tui(
                            "请输入下载路径（留空则不修改）:",
                            default=save_dir,
                        ),
                        lambda: _plain_input(
                            "请输入下载路径(留空则不修改):"
                        ),
                        "交互式输入不可用，已回退到普通输入",
                    )

                    if not new_dir:
                        print("下载路径未修改。")
                        continue

                    config.save_dir = Path(new_dir).expanduser().resolve()
                    config.save_dir.mkdir(parents=True, exist_ok=True)
                    save_config(config)
                    save_dir = str(config.save_dir)
                    print("下载路径已设置为:", save_dir)
                    continue

                if action in ("batch", "retry_failed"):
                    if action == "retry_failed":
                        urls = store.failed_urls()
                        if not urls:
                            print("没有失败项。")
                            continue
                    else:
                        lines = _try_tui(
                            use_tui_ref,
                            _read_links_tui,
                            _read_links_plain,
                            "交互式输入不可用，已回退到普通输入",
                        )
                        urls = _collect_urls(lines)
                        if not urls:
                            print("未识别到有效链接。")
                            continue

                    try:
                        session.start()
                    except RuntimeError as exc:
                        print(exc)
                        continue
                    if not session.is_logged_in():
                        print(
                            "警告：未检测到登录态，可能触发验证；"
                            "建议先执行「登录」。"
                        )

                    runner = BatchRunner(session, config, store)
                    summary = runner.run(
                        urls,
                        retry_failed=(action == "retry_failed"),
                    )
                    print(
                        f"完成：共 {summary.total}，成功 {summary.success}，"
                        f"跳过 {summary.skipped}，失败 {summary.failed}"
                    )
                    if summary.failed_urls:
                        print("失败链接：")
                        for url in summary.failed_urls:
                            print(" -", url)
                    continue

            except KeyboardInterrupt:
                print("\n程序已退出")
                break
            except Exception as exc:
                print(f"发生未预期的错误: {exc}")
                traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
