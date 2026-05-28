from douyin_spider import DouyinSpider, extract_url_from_text
from twitter_spider import TwitterSpider
import sys
import os
import re
import traceback


def detect_platform(url):
    if re.search(r'douyin\.com', url):
        return 'douyin'
    if re.search(r'x\.com|twitter\.com', url):
        return 'twitter'
    return 'unknown'

def _tui_available():
    try:
        import prompt_toolkit  # noqa: F401
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False

def _menu_tui(save_dir: str) -> str:
    """
    return action: "set_path" | "start" | "quit"
    """
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    items = [
        ("set_path", "Config download path"),
        ("start", "Start crawling videos"),
        ("quit", "Quit"),
    ]
    state = {"index": 0}

    def _render():
        lines = []
        lines.append(("class:cwd", f"{os.getcwd()}\n\n"))
        lines.append(("", "Quick safety check: Is this a project you created or one you trust?\n\n"))
        lines.append(("class:muted", f"Current save path: {save_dir}\n\n"))
        lines.append(("class:muted", "Enter to confirm | Esc to cancel\n\n"))
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
    Line input (non-dialog), closer to Claude Code style.
    - Enter: submit
    - Ctrl+C / Ctrl+D: cancel (return empty string)
    """
    from prompt_toolkit import prompt

    try:
        text = prompt(f"{prompt_text}\n> ", default=default or "")
        return (text or "").strip()
    except (KeyboardInterrupt, EOFError):
        return ""

def _menu_plain(save_dir: str) -> str:
    print("\nCurrent save path:", save_dir)
    print("Please select an option:")
    print("  1. Config download path")
    print("  2. Start crawling videos")
    print("  q. Quit")
    print("Enter option: ", end="", flush=True)
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


def _try_tui(use_tui_ref, tui_func, plain_func, fallback_msg):
    if use_tui_ref[0]:
        try:
            return tui_func()
        except Exception as e:
            print(f"Notice: {fallback_msg}. Reason: {e}")
            use_tui_ref[0] = False
    return plain_func()


def _plain_input(prompt_text, prefix=""):
    print(f"{prefix}{prompt_text} ", end="", flush=True)
    return sys.stdin.readline().strip()


def main():
    print("=" * 60)
    print("Social Media Video Crawler v2.0")
    print("Supports Douyin, Twitter/X | Auto filter ads, download HD videos")
    use_tui = _tui_available()
    if use_tui:
        print("Controls: up/down to select, Enter to confirm, Esc to quit.")
        print("Tip: Use Ctrl+C to cancel and return to menu when entering text.")
    else:
        print("Controls: Choose an option after launch. Enter 'q' to quit. (Install prompt_toolkit for arrow-key menu)")
    print("=" * 60)

    save_dir = os.path.join(os.getcwd(), "videos")
    use_tui_ref = [use_tui]

    while True:
        try:
            action = _try_tui(
                use_tui_ref,
                lambda: _menu_tui(save_dir),
                lambda: _menu_plain(save_dir),
                "Interactive menu unavailable, falling back to text menu",
            )

            if not action:
                continue

            if action == "quit":
                print("Program exited.")
                break

            if action == "invalid":
                print("Invalid option, please try again.")
                continue

            if action == "set_path":
                new_dir = _try_tui(
                    use_tui_ref,
                    lambda: _input_tui("Enter download path (leave empty to keep current):", default=save_dir),
                    lambda: _plain_input("Enter download path (leave empty to keep current):"),
                    "Interactive input unavailable, falling back to plain input",
                )

                if not new_dir:
                    print("Download path unchanged.")
                    continue

                new_dir = os.path.expandvars(os.path.expanduser(new_dir))
                os.makedirs(new_dir, exist_ok=True)
                save_dir = new_dir
                print("Download path set to:", save_dir)
                continue

            if action == "start":
                raw_input = _try_tui(
                    use_tui_ref,
                    lambda: _input_tui("Paste share link or URL:"),
                    lambda: _plain_input("Enter share link or URL:", prefix="\n"),
                    "Interactive input unavailable, falling back to plain input",
                )

                if not raw_input:
                    continue

                url = extract_url_from_text(raw_input)
                if not url:
                    print("Error: No valid URL detected, please try again.")
                    continue

                platform = detect_platform(url)
                if platform == 'douyin':
                    spider = DouyinSpider(url, save_dir=save_dir)
                elif platform == 'twitter':
                    spider = TwitterSpider(url, save_dir=save_dir)
                else:
                    print("Error: Unrecognized platform (currently supporting Douyin and Twitter/X).")
                    continue

                print(f"Starting crawler for: {url}")
                spider.run()
                print("----------------------------------------")
                continue

        except KeyboardInterrupt:
            print("\nProgram exited")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
