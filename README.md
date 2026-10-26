# Douyin Video Downloader (抖音视频下载器)

基于 Python Playwright 的抖音视频下载工具（命令行版），支持登录态复用、批量爬取、限频与断点续爬。

## 功能特点

- 自动提取分享文本中的链接
- 持久化登录态：首次扫码，之后复用浏览器 profile
- 批量多链接：逐行粘贴或从文件导入
- 两级限频：页面访问与媒体下载分别控制间隔
- 下载重试与断点续传：`.part` 文件 + HTTP Range
- 断点续爬与去重：`state.json` 记录状态，可按作品 ID 去重
- 风控识别：登录失效、验证码、无视频时给出明确提示
- 反爬加固：stealth 脚本、环境一致性、轻量行为模拟

## 环境要求

- Python 3.10+
- Windows / macOS / Linux 桌面环境
- 首次登录需要可用的图形界面

## 安装

```bash
git clone https://github.com/yyyCode/spider.git
cd spider
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Windows 一键安装：

```powershell
.\setup.cmd
```

## 运行

```bash
.\run.cmd
```

或：

```bash
python cli.py
```

菜单：

1. 登录 / 检查登录状态
2. 开始批量爬取
3. 重试失败项
4. 配置下载路径
5. 退出

## 登录

首次使用请选择「登录 / 检查登录状态」，浏览器会打开抖音首页。扫码登录成功后，程序会自动保存登录态。profile 位于 `~/.douyin-spider/profile`。

注意：

- 同一时间只能有一个程序使用该 profile。
- 默认有头模式；无头模式无法完成首次扫码。
- 登录失效时重新执行登录即可。

## 批量爬取

选择「开始批量爬取」后：

- 逐行粘贴分享文本或链接，输入空行结束；
- 输入 `@文件路径` 可从文本文件导入，每行一个链接；
- 程序会按输入顺序串行处理，并显示进度。

状态文件位于 `~/.douyin-spider/state.json`。再次运行时已成功的条目会跳过；失败项可通过「重试失败项」重新处理。

## 配置

配置文件位于 `~/.douyin-spider/config.json`，首次运行自动生成。常用字段：

| 字段 | 默认值 | 说明 |
|---|---|---|
| save_dir | `<cwd>/videos` | 下载目录 |
| headless | false | 是否无头运行；首次登录必须为 false |
| page_delay | [4.0, 9.0] | 页面访问间隔范围（秒） |
| download_delay | [1.0, 2.0] | 下载间隔范围（秒） |
| cooldown_seconds | 90 | 触发 429/风控后的冷却时间 |
| max_retries | 3 | 下载最大尝试次数 |
| page_timeout_ms | 60000 | 页面加载超时 |
| video_wait_timeout_ms | 15000 | 等待视频元素超时 |
| login_timeout_seconds | 180 | 等待扫码登录的超时 |
| min_video_size | 1048576 | 过滤小文件（广告） |
| chunk_size | 65536 | 下载分块大小 |
| human_behavior | true | 是否启用轻量行为模拟 |

## 常见问题

- **提示需要登录 / 触发验证**：执行「登录」并使用有头模式手动完成验证。
- **浏览器启动失败**：关闭其他使用同一 profile 的程序后重试。
- **下载 403**：直链过期，程序会自动重新嗅探；多次失败可重试该链接。
- **没有捕获到视频**：页面可能改版或需要登录，先检查登录态，再重试。

## 合规说明

本工具仅用于个人学习与研究。请遵守抖音平台条款、robots 协议及当地法律法规，控制访问频率，不要用于批量抓取或商业用途。

## License

MIT
