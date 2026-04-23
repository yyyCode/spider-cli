from douyin_spider import DouyinSpider, extract_url_from_text
import sys
import os

def _tui_available():
    try:
        import prompt_toolkit  # noqa: F401
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False

def _menu_tui(save_dir: str) -> str:
    """
    返回 action: "set_path" | "start" | "quit"
    """
    # 自己渲染列表，模拟 Claude Code 的 “> 1. ...” 选择风格（非 full-screen）
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    items = [
        ("set_path", "配置下载路径"),
        ("start", "开始爬取视频"),
        ("quit", "退出"),
    ]
    state = {"index": 0}

    def _render():
        lines = []
        lines.append(("class:cwd", "D:\\python\\Spider\n\n"))
        lines.append(("", "Quick safety check: Is this a project you created or one you trust?\n\n"))
        lines.append(("class:muted", f"当前下载路径: {save_dir}\n\n"))
        lines.append(("class:muted", "Enter to confirm · Esc to cancel\n\n"))
        for i, (_, label) in enumerate(items, start=1):
            if (i - 1) == state["index"]:
                lines.append(("class:selected", f"> {i}. {label}\n"))
            else:
                lines.append(("", f"  {i}. {label}\n"))
        return lines

    control = FormattedTextControl(text=_render, focusable=True, show_cursor=False)
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

    # 兼容部分终端：j/k 也可上下移动
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
    """
    行内输入（非对话框），更接近 Claude Code 风格。
    - Enter: 提交
    - Ctrl+C / Ctrl+D: 取消（返回空字符串）
    """
    from prompt_toolkit import prompt

    # prompt_toolkit 的 prompt 不支持真正的 Esc 取消（会把 Esc 当作前缀键），
    # 所以用 Ctrl+C/Ctrl+D 作为取消返回上一层的手势。
    try:
        text = prompt(f"{prompt_text}\n> ", default=default or "")
        return (text or "").strip()
    except (KeyboardInterrupt, EOFError):
        return ""

def _menu_plain(save_dir: str) -> str:
    print("\n当前下载路径:", save_dir)
    print("请选择操作：")
    print("  1. 配置下载路径")
    print("  2. 开始爬取视频")
    print("  q. 退出")
    print("请输入选项: ", end="", flush=True)
    choice = sys.stdin.readline().strip()

    if not choice:
        return ""
    if choice.lower() in ["q", "quit", "exit"]:
        return "quit"
    if choice == "1":
        return "set_path"
    if choice == "2":
        return "start"
    return "invalid"

def main():
    print("="*60)
    print("抖音视频爬虫命令行版 v1.0")
    print("功能：自动过滤广告，下载高清无水印(尽可能)视频")
    use_tui = _tui_available()
    if use_tui:
        print("操作：↑↓ 选择，Enter 确认；Esc 退出。")
        print("提示：在“输入路径/链接”时，使用 Ctrl+C 取消并返回菜单。")
    else:
        print("操作：启动后选择功能。输入 'q' 退出。（可选安装 prompt_toolkit 获得↑↓选择菜单）")
    print("="*60)

    save_dir = os.path.join(os.getcwd(), "videos")

    while True:
        try:
            if use_tui:
                try:
                    action = _menu_tui(save_dir)
                except Exception as e:
                    # 某些环境（例如无控制台/被重定向）prompt_toolkit 会报
                    print(f"提示：交互式菜单不可用，已回退到数字菜单。原因：{e}")
                    use_tui = False
                    action = _menu_plain(save_dir)
            else:
                action = _menu_plain(save_dir)

            if not action:
                continue

            if action == "quit":
                print("程序已退出。")
                break

            if action == "invalid":
                print("无效选项，请重新选择。")
                continue

            if action == "set_path":
                if use_tui:
                    try:
                        new_dir = _input_tui("请输入下载路径（留空则不修改）:", default=save_dir)
                    except Exception as e:
                        print(f"提示：交互式输入不可用，已回退到普通输入。原因：{e}")
                        use_tui = False
                        new_dir = ""
                else:
                    print("请输入下载路径(留空则不修改): ", end="", flush=True)
                    new_dir = sys.stdin.readline().strip()

                if not new_dir:
                    print("下载路径未修改。")
                    continue

                new_dir = os.path.expandvars(os.path.expanduser(new_dir))
                os.makedirs(new_dir, exist_ok=True)
                save_dir = new_dir
                print("下载路径已设置为:", save_dir)
                continue

            if action == "start":
                if use_tui:
                    try:
                        raw_input = _input_tui("请粘贴分享口令或链接：")
                    except Exception as e:
                        print(f"提示：交互式输入不可用，已回退到普通输入。原因：{e}")
                        use_tui = False
                        raw_input = ""
                else:
                    print("\n请输入分享口令或链接: ", end="", flush=True)
                    raw_input = sys.stdin.readline().strip()

                if not raw_input:
                    continue

                url = extract_url_from_text(raw_input)
                if not url:
                    print("错误: 未识别到有效链接，请重新输入。")
                    continue

                print(f"正在启动爬虫抓取: {url}")
                spider = DouyinSpider(url, save_dir=save_dir)
                spider.run()
                print("----------------------------------------")
                continue
            
        except KeyboardInterrupt:
            print("\n程序已退出")
            break
        except Exception as e:
            print(f"发生未预期的错误: {e}")

if __name__ == "__main__":
    main()
