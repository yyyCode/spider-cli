from core.douyin_spider import DouyinSpider
from core.utils import detect_platform, extract_url_from_text
from core.xhs_spider import XhsSpider

import os
import traceback

from .tui import (
    input_tui,
    menu_plain,
    menu_tui,
    plain_input,
    try_tui,
    tui_available,
)


def main():
    print("=" * 60)
    print("抖音/小红书链接爬虫命令行版 v1.0")
    print("功能：下载抖音视频，以及小红书视频或图集")
    print("提示：小红书登录墙笔记可设置环境变量 XHS_COOKIE")
    use_tui = tui_available()
    if use_tui:
        print("操作：↑↓ 选择，Enter 确认；Esc 退出。")
        print("提示：在‘输入路径/链接’时，使用 Ctrl+C 取消并返回菜单。")
    else:
        print("操作：启动后选择功能。输入 'q' 退出。（可选安装 prompt_toolkit 获得↑↓选择菜单）")
    print("=" * 60)

    save_dir = os.path.join(os.getcwd(), "videos")
    use_tui_ref = [use_tui]

    while True:
        try:
            action = try_tui(
                use_tui_ref,
                lambda: menu_tui(save_dir),
                lambda: menu_plain(save_dir),
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

            if action == "set_path":
                new_dir = try_tui(
                    use_tui_ref,
                    lambda: input_tui("请输入下载路径（留空则不修改）:", default=save_dir),
                    lambda: plain_input("请输入下载路径(留空则不修改):"),
                    "交互式输入不可用，已回退到普通输入",
                )

                if not new_dir:
                    print("下载路径未修改。")
                    continue

                new_dir = os.path.expandvars(os.path.expanduser(new_dir))
                os.makedirs(new_dir, exist_ok=True)
                save_dir = new_dir
                print("下载路径已设置为:", save_dir)
                continue

            if action == "start":
                raw_input = try_tui(
                    use_tui_ref,
                    lambda: input_tui("请粘贴分享口令或链接："),
                    lambda: plain_input("请输入分享口令或链接:", prefix="\n"),
                    "交互式输入不可用，已回退到普通输入",
                )

                if not raw_input:
                    continue

                url = extract_url_from_text(raw_input)
                if not url:
                    print("错误: 未识别到有效链接，请重新输入。")
                    continue

                platform = detect_platform(url)
                if platform == "douyin":
                    spider = DouyinSpider(url, save_dir=save_dir)
                elif platform == "xhs":
                    spider = XhsSpider(
                        url,
                        save_dir=save_dir,
                        cookie=os.environ.get("XHS_COOKIE"),
                    )
                else:
                    print("错误: 仅支持抖音和小红书链接。")
                    continue

                print(f"正在启动爬虫抓取: {url}")
                spider.run()
                print("----------------------------------------")
                continue

        except KeyboardInterrupt:
            print("\n程序已退出")
            break
        except Exception as e:
            print(f"发生未预期的错误: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
