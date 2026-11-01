"""Terminal interaction helpers: interactive menus and line input."""

import os
import sys


def tui_available():
    try:
        import prompt_toolkit  # noqa: F401
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def menu_tui(save_dir: str) -> str:
    """
    返回 action: "set_path" | "start" | "quit"
    """
    # 自己渲染列表，模拟 Claude Code 的 "> 1. ..." 选择风格（非 full-screen）
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    items = [
        ("set_path", "配置下载路径"),
        ("start", "开始爬取链接"),
        ("quit", "退出"),
    ]
    state = {"index": 0}

    def _render():
        lines = []
        lines.append(("class:cwd", f"{os.getcwd()}\n\n"))
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


def input_tui(prompt_text: str, default: str = "") -> str:
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


def menu_plain(save_dir: str) -> str:
    print("\n当前下载路径:", save_dir)
    print("请选择操作：")
    print("  1. 配置下载路径")
    print("  2. 开始爬取链接")
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


def try_tui(use_tui_ref, tui_func, plain_func, fallback_msg):
    if use_tui_ref[0]:
        try:
            return tui_func()
        except Exception as e:
            print(f"提示：{fallback_msg}。原因：{e}")
            use_tui_ref[0] = False
    return plain_func()


def plain_input(prompt_text, prefix=""):
    print(f"{prefix}{prompt_text} ", end="", flush=True)
    return sys.stdin.readline().strip()
