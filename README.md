<div align="center">

# 抖音视频下载器

基于 Python Playwright 的抖音视频下载命令行工具。粘贴分享口令即可自动提取链接，抓取页面加载的视频流并保存到本地。

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/playwright-1.x-2EAD33.svg)](https://playwright.dev/python/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#贡献)

[功能特性](#功能特性) · [快速开始](#快速开始) · [使用说明](#使用说明) · [工作原理](#工作原理) · [常见问题](#常见问题)

</div>

## 功能特性

- 直接粘贴完整的分享文本，自动从中文和表情符号中提取第一个 http/https 链接
- 监听页面发出的网络请求，在多个候选视频流中按体积选择最大的一个
- 忽略小于 1 MB 的视频流，跳过大部分广告和特效小文件
- 注入 `stealth.min.js`，配合桌面 UA 和鼠标移动模拟，降低被识别为机器人的概率
- 基于 `prompt_toolkit` 的方向键菜单，终端不支持交互时自动回退为数字菜单
- 下载目录可随时修改，文件名取自视频标题并过滤非法字符

## 界面预览

```text
E:\python\spider-cli

当前下载路径: E:\python\spider-cli\videos

Enter to confirm · Esc to cancel

> 1. 配置下载路径
  2. 开始爬取视频
  3. 退出
```

## 环境要求

- Python 3.8 或更高版本
- 网络可以正常访问 douyin.com
- Windows 可以直接使用仓库内的 `.cmd` 脚本；macOS 和 Linux 按手动步骤安装

## 快速开始

### 方式一：一键安装（Windows）

```powershell
git clone https://github.com/yyyCode/spider-cli.git
cd spider-cli
.\setup.cmd
.\run.cmd
```

`setup.cmd` 会依次完成以下操作：

1. 在项目目录创建 `.venv` 虚拟环境
2. 升级 pip、setuptools 和 wheel
3. 安装 `requirements.txt` 中的依赖
4. 下载 Playwright Chromium 浏览器

### 方式二：手动安装

```bash
git clone https://github.com/yyyCode/spider-cli.git
cd spider-cli

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium

python cli.py
```

> 如果终端没有安装 `prompt_toolkit`，程序会使用数字菜单，功能不受影响。

## 使用说明

启动后可以选择三个操作：

- 配置下载路径：输入新目录，留空表示保持不变。默认目录是当前工作目录下的 `videos/`
- 开始爬取视频：粘贴抖音分享口令或链接，程序提取链接后开始下载
- 退出：结束程序

### 按键

| 场景 | 按键 | 说明 |
| --- | --- | --- |
| 菜单移动 | `↑` / `↓` 或 `j` / `k` | 在选项间切换 |
| 菜单确认 | `Enter` | 执行当前选项 |
| 退出菜单 | `Esc` | 等同选择"退出" |
| 输入提交 | `Enter` | 提交路径或链接 |
| 输入取消 | `Ctrl+C` / `Ctrl+D` | 放弃输入并返回菜单 |

### 跳过菜单

只想下载单个链接时，可以直接运行爬虫模块：

```bash
python douyin_spider.py
```

按提示粘贴分享文本即可，文件会保存到 `videos/`。

### 作为库调用

```python
from douyin_spider import DouyinSpider, extract_url_from_text

text = "复制来的分享口令 https://v.douyin.com/xxxxxx/ ..."
url = extract_url_from_text(text)

spider = DouyinSpider(url, save_dir="my_videos", headless=True)
spider.run()
```

`headless=False` 会打开浏览器窗口，方便观察抓取过程。也可以传入 `log_callback` 接管日志输出：

```python
spider = DouyinSpider(url, log_callback=print)
```

## 工作原理

1. 用正则从输入文本中提取第一个 http/https 链接
2. Playwright 启动 Chromium，设置 1920x1080 视口和桌面 UA，并注入 `stealth.min.js`
3. 打开视频页，监听响应中的 `video/mp4` 内容或 `.mp4` 请求，记录大小超过 1 MB 的候选
4. 等待 `video` 元素和 `networkidle`，期间移动鼠标触发资源加载
5. 候选按大小排序取最大的一条；没有候选时回退读取 `video` 或 `source` 标签的 `src`
6. 使用 `requests` 流式下载，请求头带上 `Referer` 和 UA，保存为 `<标题>.mp4`

## 项目结构

```text
spider-cli/
├── cli.py                 # 命令行入口与交互菜单
├── douyin_spider.py       # 爬虫核心
├── stealth.min.js         # 反检测注入脚本
├── test_spider.py         # pytest 测试
├── requirements.txt       # 运行依赖
├── requirements-dev.txt   # 打包依赖
├── setup.cmd              # Windows 一键安装
├── run.cmd                # Windows 一键运行
├── docs/                  # 设计与实施文档
└── videos/                # 默认下载目录（已加入 .gitignore）
```

## 配置项

抓取参数集中定义在 `DouyinSpider` 类中，需要调整时直接修改这些常量：

| 常量 | 默认值 | 作用 |
| --- | --- | --- |
| `MIN_VIDEO_SIZE` | 1 MB | 小于该体积的视频流会被忽略 |
| `CHUNK_SIZE` | 8192 | 下载分块大小 |
| `PAGE_TIMEOUT` | 60 秒 | 页面加载超时 |
| `VIDEO_WAIT_TIMEOUT` | 15 秒 | 等待 `video` 元素的超时 |
| `MOUSE_MOVE_WAIT` | 2 秒 | 模拟鼠标后的等待时间 |
| `MAX_TITLE_LEN` | 50 | 文件名最大长度 |
| `VIEWPORT_WIDTH` / `VIEWPORT_HEIGHT` | 1920 x 1080 | 浏览器视口尺寸 |

## 测试

```bash
pip install pytest
pytest -v
```

现有测试覆盖链接提取、构造参数和类常量，不需要网络，也不会启动浏览器。

## 常见问题

**提示"未识别到有效链接"**

输入内容中需要包含完整的 `http://` 或 `https://` 链接。抖音 App 复制的口令一般自带短链接，直接整段粘贴即可。

**抓不到视频，提示 blob 格式**

部分视频使用 blob 加密流，无法用当前方式直接下载。可以先用 `headless=False` 打开浏览器观察页面是否正常播放，并确认该视频不需要登录。

**提示启动浏览器失败**

多半是 Chromium 没有安装。运行 `playwright install chromium` 后重试。

**下载下来的文件很小或内容不对**

程序会忽略小于 1 MB 的视频流。如果页面本身只提供低码率流，得到的就是这个版本。

**方向键菜单没有出现**

终端不是交互式环境，或没有安装 `prompt_toolkit`。此时会自动切换到数字菜单，输入 `1`、`2` 或 `q` 即可。

## 免责声明

本项目仅供学习和研究使用。请遵守抖音的服务条款和当地法律法规，不要用于批量抓取、商业分发或传播他人作品。下载内容的版权归原作者所有。

## 贡献

欢迎提交 Issue 和 Pull Request。

1. Fork 仓库并创建分支：`git checkout -b feat/your-feature`
2. 修改代码并补充测试
3. 运行 `pytest` 确认通过
4. 提交 PR，说明改动内容和使用场景

保持每次 PR 只解决一个问题，方便 review。

## License

本项目基于 [MIT License](https://opensource.org/licenses/MIT) 开源。

<div align="center">

如果这个工具帮你省了时间，点个 Star 就是最好的支持。

</div>
