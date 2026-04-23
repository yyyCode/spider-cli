# Douyin Video Downloader (抖音视频下载器)

一个基于 Python Playwright 的抖音视频下载工具（命令行版）。

## ✨ 功能特点

*   **自动提取链接**：支持直接粘贴包含中文、表情符号的混合分享文本，自动提取 URL。
*   **高清无水印**：自动嗅探并下载高清无水印视频。
*   **智能防检测**：内置 stealth 脚本和动态行为模拟，有效规避反爬检测。

## 🛠️ 本地开发与运行

如果你想自己修改代码或从源码运行：

### 1. 克隆仓库
```bash
git clone https://github.com/yyyCode/spider.git
cd spider
```

### 2. 安装依赖
确保已安装 Python 3.8+，然后运行：
```bash
pip install -r requirements.txt
```

### 3. 安装浏览器驱动
```bash
playwright install chromium
```

### （推荐）一条命令一键安装依赖（Windows）
在项目根目录运行：
```powershell
.\setup.cmd
```

> `setup.cmd` 为纯 CMD 脚本，不依赖 PowerShell。

### 4. 运行
**命令行模式**
```bash
.\run.cmd
```

启动后会显示菜单：
- 推荐交互：**↑↓ 选择，Enter 确认**（基于 `prompt_toolkit`）
- 如果终端不支持交互式菜单，会自动回退为数字菜单：
  - 1：配置下载路径（默认当前目录下 `videos/`）
  - 2：开始爬取视频（粘贴分享口令或链接）
  - q：退出

交互说明：
- **菜单页**：↑↓（或 j/k）移动，Enter 确认，Esc 退出
- **输入下载路径/链接时**：Enter 提交，**Ctrl+C 取消并返回菜单**（留空表示不修改）

## 📝 License

MIT
